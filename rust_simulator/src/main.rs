use anyhow::{Context, Result, bail};
use csv::{ReaderBuilder, WriterBuilder};
use rand::distributions::{Distribution, WeightedIndex};
use rand::{Rng, SeedableRng};
use rand_chacha::ChaCha8Rng;
use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::env;
use std::fs;
use std::io::{BufRead, BufReader, BufWriter, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};

pub mod config;
pub mod dro;
mod posterior;
mod products;

const DAYS: [i32; 2] = [-2, -1];
const DEFAULT_TICKS_PER_DAY: usize = 10_000;
const TIMESTAMP_STEP: i32 = 100;
const STRATEGY_RUN_TIMEOUT_MS: u64 = 900;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum FvMode {
    Replay,
    Simulate,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum TradeMode {
    ReplayTimes,
    Simulate,
}

#[derive(Clone, Debug)]
struct Config {
    output_dir: PathBuf,
    actual_dir: PathBuf,
    fv_mode: FvMode,
    trade_mode: TradeMode,
    seed: u64,
    strategy_path: Option<PathBuf>,
    python_bin: String,
    sessions: usize,
    write_session_limit: usize,
    ticks_per_day: usize,
    sim_config: config::SimConfig,
    fixed_params: bool,
    dro: bool,
    dro_radius: f64,
    dro_k: usize,
}

#[derive(Clone, Debug)]
struct ReplayData {
    tomato_fair_by_day: HashMap<i32, Vec<f64>>,
    trade_counts_by_key: HashMap<(i32, String), Vec<usize>>,
}

#[derive(Clone, Debug)]
struct DayOutput {
    day: i32,
    price_rows: Vec<PriceRow>,
    trade_rows: Vec<TradeRow>,
    trace_rows: Vec<TraceRow>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum LevelOwner {
    Bot,
    Strategy,
}

#[derive(Clone, Debug)]
struct Level {
    price: i32,
    quantity: i32,
    owner: LevelOwner,
}

#[derive(Clone, Debug)]
struct SimBook {
    bids: Vec<Level>,
    asks: Vec<Level>,
}

#[derive(Clone, Debug)]
struct Fill {
    symbol: String,
    price: i32,
    quantity: i32,
    buyer: Option<String>,
    seller: Option<String>,
    timestamp: i32,
}

#[derive(Clone, Debug, Default)]
struct ProductLedger {
    position: i32,
    cash: f64,
}

#[derive(Clone, Copy, Debug, Default)]
struct RunningLinearFit {
    n: f64,
    sum_x: f64,
    sum_y: f64,
    sum_xx: f64,
    sum_yy: f64,
    sum_xy: f64,
}

impl RunningLinearFit {
    fn update(&mut self, x: f64, y: f64) {
        self.n += 1.0;
        self.sum_x += x;
        self.sum_y += y;
        self.sum_xx += x * x;
        self.sum_yy += y * y;
        self.sum_xy += x * y;
    }

    fn slope_per_step(&self) -> f64 {
        let denom = self.n * self.sum_xx - self.sum_x * self.sum_x;
        if denom.abs() < 1e-12 {
            0.0
        } else {
            (self.n * self.sum_xy - self.sum_x * self.sum_y) / denom
        }
    }

    fn r_squared(&self) -> f64 {
        let x_var = self.n * self.sum_xx - self.sum_x * self.sum_x;
        let y_var = self.n * self.sum_yy - self.sum_y * self.sum_y;
        if x_var.abs() < 1e-12 || y_var.abs() < 1e-12 {
            0.0
        } else {
            let cov = self.n * self.sum_xy - self.sum_x * self.sum_y;
            (cov * cov) / (x_var * y_var)
        }
    }
}

#[derive(Clone, Debug)]
struct SessionSummary {
    session_id: usize,
    total_pnl: f64,
    per_product_pnl: HashMap<String, f64>,
    per_product_position: HashMap<String, i32>,
    per_product_cash: HashMap<String, f64>,
    per_product_slope_per_step: HashMap<String, f64>,
    per_product_r2: HashMap<String, f64>,
    total_slope_per_step: f64,
    total_r2: f64,
}

#[derive(Clone, Debug)]
struct RunSummary {
    session_id: usize,
    day: i32,
    total_pnl: f64,
    per_product_pnl: HashMap<String, f64>,
    per_product_slope_per_step: HashMap<String, f64>,
    per_product_r2: HashMap<String, f64>,
    total_slope_per_step: f64,
    total_r2: f64,
}

#[derive(Clone, Debug)]
struct SessionOutput {
    session_id: usize,
    summary: SessionSummary,
    run_summaries: Vec<RunSummary>,
    day_outputs: Vec<DayOutput>,
    dro_session_report: Option<dro::DroSessionReport>,
}

#[derive(Clone, Debug)]
struct Book {
    bids: Vec<(i32, i32)>,
    asks: Vec<(i32, i32)>,
}

#[allow(dead_code)]
#[derive(Debug, Deserialize)]
struct InputPriceRow {
    day: i32,
    timestamp: i32,
    product: String,
    bid_price_1: Option<i32>,
    bid_volume_1: Option<i32>,
    bid_price_2: Option<i32>,
    bid_volume_2: Option<i32>,
    bid_price_3: Option<i32>,
    bid_volume_3: Option<i32>,
    ask_price_1: Option<i32>,
    ask_volume_1: Option<i32>,
    ask_price_2: Option<i32>,
    ask_volume_2: Option<i32>,
    ask_price_3: Option<i32>,
    ask_volume_3: Option<i32>,
    mid_price: f64,
    profit_and_loss: f64,
}

#[allow(dead_code)]
#[derive(Debug, Deserialize)]
struct InputTradeRow {
    timestamp: i32,
    buyer: Option<String>,
    seller: Option<String>,
    symbol: String,
    currency: String,
    price: f64,
    quantity: i32,
}

#[derive(Clone, Debug, Serialize)]
struct PriceRow {
    day: i32,
    timestamp: i32,
    product: String,
    bid_price_1: Option<i32>,
    bid_volume_1: Option<i32>,
    bid_price_2: Option<i32>,
    bid_volume_2: Option<i32>,
    bid_price_3: Option<i32>,
    bid_volume_3: Option<i32>,
    ask_price_1: Option<i32>,
    ask_volume_1: Option<i32>,
    ask_price_2: Option<i32>,
    ask_volume_2: Option<i32>,
    ask_price_3: Option<i32>,
    ask_volume_3: Option<i32>,
    mid_price: f64,
    profit_and_loss: f64,
}

#[derive(Clone, Debug, Serialize)]
struct TradeRow {
    timestamp: i32,
    buyer: Option<String>,
    seller: Option<String>,
    symbol: String,
    currency: String,
    price: f64,
    quantity: i32,
}

#[derive(Clone, Debug, Serialize)]
struct TraceRow {
    day: i32,
    timestamp: i32,
    product: String,
    fair_value: f64,
    position: i32,
    cash: f64,
    mtm_pnl: f64,
}

#[derive(Debug, Serialize)]
struct WorkerTrade {
    symbol: String,
    price: i32,
    quantity: i32,
    buyer: Option<String>,
    seller: Option<String>,
    timestamp: i32,
}

#[derive(Debug, Serialize)]
struct WorkerOrderDepth {
    buy_orders: HashMap<String, i32>,
    sell_orders: HashMap<String, i32>,
}

#[derive(Debug, Serialize)]
struct WorkerRequest {
    #[serde(rename = "type")]
    request_type: String,
    timestamp: i32,
    timeout_ms: u64,
    trader_data: String,
    order_depths: HashMap<String, WorkerOrderDepth>,
    own_trades: HashMap<String, Vec<WorkerTrade>>,
    market_trades: HashMap<String, Vec<WorkerTrade>>,
    position: HashMap<String, i32>,
}

#[allow(dead_code)]
#[derive(Clone, Debug, Deserialize)]
struct WorkerOrder {
    symbol: String,
    price: i32,
    quantity: i32,
}

#[allow(dead_code)]
#[derive(Debug, Deserialize)]
struct WorkerResponse {
    orders: Option<HashMap<String, Vec<WorkerOrder>>>,
    conversions: Option<i32>,
    trader_data: Option<String>,
    stdout: Option<String>,
    error: Option<String>,
}

impl Config {
    fn from_args() -> Result<Self> {
        let mut output_dir = PathBuf::from("../tmp/rust_simulator_output");
        let mut actual_dir = PathBuf::from("../data/round0");
        let mut fv_mode = FvMode::Replay;
        let mut trade_mode = TradeMode::ReplayTimes;
        let mut seed: u64 = 20_260_401;
        let mut strategy_path: Option<PathBuf> = None;
        let mut python_bin = "python3".to_string();
        let mut sessions: usize = 1;
        let mut write_session_limit: usize = 0;
        let mut ticks_per_day: usize = DEFAULT_TICKS_PER_DAY;
        let mut config_path: Option<String> = None;
        let mut fixed_params = false;
        let mut dro = false;
        let mut dro_radius: f64 = 2.0;
        let mut dro_k: usize = 8;

        let mut args = env::args().skip(1);
        while let Some(arg) = args.next() {
            match arg.as_str() {
                "--output" => {
                    output_dir =
                        PathBuf::from(args.next().context("missing value for --output")?);
                }
                "--actual-dir" => {
                    actual_dir =
                        PathBuf::from(args.next().context("missing value for --actual-dir")?);
                }
                "--fv-mode" => {
                    let value = args.next().context("missing value for --fv-mode")?;
                    fv_mode = match value.as_str() {
                        "replay" => FvMode::Replay,
                        "simulate" => FvMode::Simulate,
                        other => bail!("unsupported --fv-mode {}", other),
                    };
                }
                "--trade-mode" => {
                    let value = args.next().context("missing value for --trade-mode")?;
                    trade_mode = match value.as_str() {
                        "replay-times" => TradeMode::ReplayTimes,
                        "simulate" => TradeMode::Simulate,
                        other => bail!("unsupported --trade-mode {}", other),
                    };
                }
                "--tomato-support" => {
                    // deprecated; accepted but ignored
                    let _ = args.next().context("missing value for --tomato-support")?;
                }
                "--seed" => {
                    seed = args
                        .next()
                        .context("missing value for --seed")?
                        .parse()
                        .context("invalid --seed")?;
                }
                "--strategy" => {
                    strategy_path = Some(PathBuf::from(
                        args.next().context("missing value for --strategy")?,
                    ));
                }
                "--python-bin" => {
                    python_bin = args.next().context("missing value for --python-bin")?;
                }
                "--sessions" => {
                    sessions = args
                        .next()
                        .context("missing value for --sessions")?
                        .parse()
                        .context("invalid --sessions")?;
                }
                "--write-session-limit" => {
                    write_session_limit = args
                        .next()
                        .context("missing value for --write-session-limit")?
                        .parse()
                        .context("invalid --write-session-limit")?;
                }
                "--ticks-per-day" => {
                    ticks_per_day = args
                        .next()
                        .context("missing value for --ticks-per-day")?
                        .parse()
                        .context("invalid --ticks-per-day")?;
                }
                "--config" => {
                    config_path = Some(args.next().context("missing value for --config")?);
                }
                "--fixed-params" => {
                    fixed_params = true;
                }
                "--dro" => {
                    dro = true;
                }
                "--dro-radius" => {
                    dro_radius = args
                        .next()
                        .context("missing value for --dro-radius")?
                        .parse()
                        .context("invalid --dro-radius")?;
                }
                "--dro-k" => {
                    dro_k = args
                        .next()
                        .context("missing value for --dro-k")?
                        .parse()
                        .context("invalid --dro-k")?;
                }
                other => bail!("unknown argument {}", other),
            }
        }

        // resolve project root: prefer env var set by Python CLI, fall back to cwd parent
        let project_root: PathBuf = env::var("PROSPERITY4MCBT_ROOT")
            .map(PathBuf::from)
            .unwrap_or_else(|_| {
                env::current_dir()
                    .map(|cwd| cwd.parent().map(Path::to_path_buf).unwrap_or(cwd))
                    .unwrap_or_else(|_| PathBuf::from("."))
            });

        let cfg_resolved: PathBuf = match config_path {
            Some(ref p) => PathBuf::from(p),
            None => project_root.join("configs/tutorial.toml"),
        };
        let cfg_text = fs::read_to_string(&cfg_resolved)
            .with_context(|| format!("read {}", cfg_resolved.display()))?;
        let sim_config: config::SimConfig = toml::from_str(&cfg_text)
            .with_context(|| format!("parse {}", cfg_resolved.display()))?;

        Ok(Config {
            output_dir,
            actual_dir,
            fv_mode,
            trade_mode,
            seed,
            strategy_path,
            python_bin,
            sessions,
            write_session_limit,
            ticks_per_day,
            sim_config,
            fixed_params,
            dro,
            dro_radius,
            dro_k,
        })
    }
}

fn main() -> Result<()> {
    let config = Config::from_args()?;
    let replay_data = ReplayData::load(&config)?;

    if config.strategy_path.is_some() {
        let (outputs, dro_report) = run_backtests(&config, &replay_data)?;
        write_backtest_outputs(&config, &outputs)?;
        if let Some(report) = dro_report {
            write_dro_report(&config, &report)?;
        }
        write_run_log(&config)?;
        return Ok(());
    }

    let outputs = DAYS
        .par_iter()
        .map(|day| generate_day(*day, &config, &replay_data))
        .collect::<Result<Vec<_>>>()?;

    write_outputs(&config, &outputs)?;
    write_run_log(&config)?;
    Ok(())
}

impl ReplayData {
    fn load(config: &Config) -> Result<Self> {
        let mut tomato_fair_by_day = HashMap::new();
        let mut trade_counts_by_key = HashMap::new();

        if config.fv_mode == FvMode::Replay {
            for day in DAYS {
                let prices = load_price_rows(&config.actual_dir, day)?;
                let mut rows: Vec<_> = prices
                    .into_iter()
                    .filter(|row| row.product == "TOMATOES")
                    .collect();
                rows.sort_by_key(|row| row.timestamp);
                let fair_series = rows
                    .iter()
                    .map(estimate_tomato_fair)
                    .collect::<Vec<_>>();
                tomato_fair_by_day.insert(day, fair_series);
            }
        }

        if config.trade_mode == TradeMode::ReplayTimes {
            for day in DAYS {
                let trades = load_trade_rows(&config.actual_dir, day)?;
                for pc in &config.sim_config.products {
                    let product = pc.name.as_str();
                    let mut counts = vec![0usize; DEFAULT_TICKS_PER_DAY];
                    for trade in trades.iter().filter(|row| row.symbol == product) {
                        let index = usize::try_from(trade.timestamp / TIMESTAMP_STEP)
                            .context("negative timestamp while loading replay trades")?;
                        if index < counts.len() {
                            counts[index] += 1;
                        }
                    }
                    trade_counts_by_key.insert((day, product.to_string()), counts);
                }
            }
        }

        Ok(Self {
            tomato_fair_by_day,
            trade_counts_by_key,
        })
    }
}

fn generate_day(day: i32, config: &Config, replay: &ReplayData) -> Result<DayOutput> {
    let mut rng = ChaCha8Rng::seed_from_u64(seed_for_day(config.seed, day));
    let tomato_fair = match config.fv_mode {
        FvMode::Replay => replay
            .tomato_fair_by_day
            .get(&day)
            .cloned()
            .context("missing replay tomato fair series")?,
        FvMode::Simulate => simulate_tomato_fair_series(day, config.ticks_per_day, &mut rng),
    };

    // sample per-session params for each product
    let sampled_products: Vec<config::SampledProductParams> = config
        .sim_config
        .products
        .iter()
        .map(|pc| {
            if config.fixed_params {
                pc.to_point_estimate()
            } else {
                pc.sample_from_posterior(&mut rng)
            }
        })
        .collect();

    // pre-compute trade counts per product
    let mut trade_counts_per_product: Vec<Vec<usize>> = Vec::with_capacity(sampled_products.len());
    for sampled in &sampled_products {
        let counts = trade_counts_for(sampled, day, config, replay, &mut rng)?;
        trade_counts_per_product.push(counts);
    }

    let mut price_rows = Vec::with_capacity(config.ticks_per_day * sampled_products.len());
    let mut trade_rows = Vec::new();

    for tick in 0..config.ticks_per_day {
        let timestamp = (tick as i32) * TIMESTAMP_STEP;

        for (i, sampled) in sampled_products.iter().enumerate() {
            let fv_for_book = if sampled.name == "TOMATOES" {
                tomato_fair[tick]
            } else {
                sampled_fv_at_tick(sampled, tick)
            };
            let book = make_book(sampled, fv_for_book, &mut rng);
            price_rows.push(book_to_price_row(day, timestamp, &sampled.name, &book));

            for _ in 0..trade_counts_per_product[i][tick] {
                trade_rows.extend(sample_trade_rows(timestamp, sampled, &book, &mut rng));
            }
        }
    }

    price_rows.sort_by(|a, b| {
        a.timestamp
            .cmp(&b.timestamp)
            .then(a.product.cmp(&b.product))
    });
    trade_rows.sort_by(|a, b| a.timestamp.cmp(&b.timestamp).then(a.symbol.cmp(&b.symbol)));

    Ok(DayOutput {
        day,
        price_rows,
        trade_rows,
        trace_rows: Vec::new(),
    })
}

/// Returns current fair value for a product at a given tick.
/// For TOMATOES we use the latent state vector; for fixed/OU we use the sampled initial.
/// (full per-tick stepping is only done in the backtest session loop.)
fn sampled_fv_at_tick(sampled: &config::SampledProductParams, _tick: usize) -> f64 {
    match &sampled.fv_process {
        config::SampledFvProcess::Fixed { price } => *price,
        config::SampledFvProcess::DriftingWalk { initial, .. } => *initial,
        config::SampledFvProcess::MeanRevertOU { center, .. } => *center,
    }
}

fn write_outputs(config: &Config, outputs: &[DayOutput]) -> Result<()> {
    let round_dir = config.output_dir.join("round0");
    fs::create_dir_all(&round_dir)
        .with_context(|| format!("failed to create {}", round_dir.display()))?;

    for output in outputs {
        let price_path = round_dir.join(format!("prices_round_0_day_{}.csv", output.day));
        let trade_path = round_dir.join(format!("trades_round_0_day_{}.csv", output.day));

        let mut price_writer = WriterBuilder::new()
            .delimiter(b';')
            .from_path(&price_path)
            .with_context(|| format!("failed to open {}", price_path.display()))?;
        for row in &output.price_rows {
            price_writer.serialize(row)?;
        }
        price_writer.flush()?;

        let mut trade_writer = WriterBuilder::new()
            .delimiter(b';')
            .from_path(&trade_path)
            .with_context(|| format!("failed to open {}", trade_path.display()))?;
        for row in &output.trade_rows {
            trade_writer.serialize(row)?;
        }
        trade_writer.flush()?;
    }

    Ok(())
}

struct StrategyWorker {
    child: Child,
    stdin: BufWriter<ChildStdin>,
    stdout: BufReader<ChildStdout>,
}

impl StrategyWorker {
    fn spawn(config: &Config) -> Result<Self> {
        let strategy_path = config
            .strategy_path
            .as_ref()
            .context("missing strategy path")?
            .canonicalize()
            .with_context(|| "failed to canonicalize strategy path")?;
        let project_root = env::var("PROSPERITY4MCBT_ROOT")
            .map(PathBuf::from)
            .or_else(|_| {
                env::current_dir().map(|cwd| {
                    cwd.parent()
                        .map(Path::to_path_buf)
                        .unwrap_or(cwd)
                })
            })
            .context("failed to resolve project root for python strategy worker")?;
        let worker_path = project_root.join("scripts/python_strategy_worker.py");
        if !worker_path.is_file() {
            bail!(
                "python strategy worker not found at {}",
                worker_path.display()
            );
        }

        let mut child = Command::new(&config.python_bin)
            .arg(worker_path)
            .arg(strategy_path)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .context("failed to spawn python strategy worker")?;

        let stdin = BufWriter::new(child.stdin.take().context("missing worker stdin")?);
        let stdout = BufReader::new(child.stdout.take().context("missing worker stdout")?);

        Ok(Self {
            child,
            stdin,
            stdout,
        })
    }

    fn reset(&mut self) -> Result<()> {
        let payload = serde_json::json!({ "type": "reset" });
        self.send(&payload)?;
        let response = self.read_response()?;
        if let Some(error) = response.error {
            bail!("python worker reset failed: {}", error);
        }
        Ok(())
    }

    fn run(&mut self, request: &WorkerRequest) -> Result<WorkerResponse> {
        self.send(request)?;
        let response = self.read_response()?;
        if let Some(error) = &response.error {
            bail!("python worker failed: {}", error);
        }
        Ok(response)
    }

    fn send<T: Serialize>(&mut self, payload: &T) -> Result<()> {
        serde_json::to_writer(&mut self.stdin, payload)?;
        self.stdin.write_all(b"\n")?;
        self.stdin.flush()?;
        Ok(())
    }

    fn read_response(&mut self) -> Result<WorkerResponse> {
        let mut line = String::new();
        let bytes = self.stdout.read_line(&mut line)?;
        if bytes == 0 {
            bail!("python worker exited unexpectedly");
        }
        let response = serde_json::from_str::<WorkerResponse>(line.trim())
            .context("failed to decode python worker response")?;
        Ok(response)
    }
}

impl Drop for StrategyWorker {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

fn run_backtests(config: &Config, replay: &ReplayData) -> Result<(Vec<SessionOutput>, Option<dro::DroReport>)> {
    let mut outputs = (0..config.sessions)
        .into_par_iter()
        .map(|session_id| {
            run_backtest_session(session_id, session_id < config.write_session_limit, config, replay)
        })
        .collect::<Result<Vec<_>>>()?;
    outputs.sort_by_key(|output| output.session_id);

    let dro_report = if config.dro {
        let session_reports: Vec<dro::DroSessionReport> = outputs
            .iter()
            .map(|o| o.dro_session_report.clone().expect("dro enabled but report missing"))
            .collect();
        Some(dro::aggregate(session_reports, config.dro_radius, config.dro_k))
    } else {
        None
    };

    Ok((outputs, dro_report))
}

fn monte_carlo_session_day(session_id: usize) -> i32 {
    DAYS[session_id % DAYS.len()]
}

/// Result of simulating one day with given sampled products.
struct DaySimResult {
    per_product_pnl: HashMap<String, f64>,
    per_product_cash: HashMap<String, f64>,
    per_product_position: HashMap<String, i32>,
    day_output: DayOutput,
    day_total_fit: RunningLinearFit,
    day_product_fits: HashMap<String, RunningLinearFit>,
}

/// Runs the full tick loop for one day with the given sampled products.
/// Resets the worker before running.
fn simulate_day(
    worker: &mut StrategyWorker,
    sampled_products: &[config::SampledProductParams],
    product_names: &[String],
    config: &Config,
    replay: &ReplayData,
    day: i32,
    rng: &mut ChaCha8Rng,
    capture_outputs: bool,
) -> Result<DaySimResult> {
    worker.reset()?;

    let mut fv_states: Vec<products::FvState> = sampled_products
        .iter()
        .map(|s| products::FvState::initial(&s.fv_process))
        .collect();

    let tomato_fair = match config.fv_mode {
        FvMode::Replay => replay
            .tomato_fair_by_day
            .get(&day)
            .cloned()
            .context("missing replay tomato fair series")?,
        FvMode::Simulate => simulate_tomato_fair_series(day, config.ticks_per_day, rng),
    };

    let mut trade_counts_per_product: Vec<Vec<usize>> = Vec::with_capacity(sampled_products.len());
    for sampled in sampled_products {
        let counts = trade_counts_for(sampled, day, config, replay, rng)?;
        trade_counts_per_product.push(counts);
    }

    let mut ledgers: HashMap<String, ProductLedger> = sampled_products
        .iter()
        .map(|s| (s.name.clone(), ProductLedger::default()))
        .collect();

    let mut trader_data = String::new();
    let mut prev_own_trades: HashMap<String, Vec<Fill>> = empty_trade_map(product_names);
    let mut prev_market_trades: HashMap<String, Vec<Fill>> = empty_trade_map(product_names);
    let mut day_total_fit = RunningLinearFit::default();
    let mut day_product_fits: HashMap<String, RunningLinearFit> = product_names
        .iter()
        .map(|n| (n.clone(), RunningLinearFit::default()))
        .collect();
    let mut day_step = 0usize;
    let mut price_rows = if capture_outputs {
        Vec::with_capacity(config.ticks_per_day * sampled_products.len())
    } else {
        Vec::new()
    };
    let mut trade_rows = Vec::new();
    let mut trace_rows = Vec::new();

    for tick in 0..config.ticks_per_day {
        let timestamp = (tick as i32) * TIMESTAMP_STEP;

        for (i, sampled) in sampled_products.iter().enumerate() {
            fv_states[i].step(&sampled.fv_process, rng);
        }

        let books: Vec<Book> = sampled_products.iter().enumerate().map(|(i, sampled)| {
            let fv = if sampled.name == "TOMATOES" {
                tomato_fair[tick]
            } else {
                fv_states[i].current
            };
            make_book(sampled, fv, rng)
        }).collect();

        if capture_outputs {
            for (i, sampled) in sampled_products.iter().enumerate() {
                price_rows.push(book_to_price_row(day, timestamp, &sampled.name, &books[i]));
            }
        }

        let order_depths: HashMap<String, WorkerOrderDepth> = sampled_products
            .iter()
            .enumerate()
            .map(|(i, s)| (s.name.clone(), book_to_worker_depth(&books[i])))
            .collect();

        let position = ledgers
            .iter()
            .map(|(product, ledger)| (product.clone(), ledger.position))
            .collect::<HashMap<_, _>>();

        let request = WorkerRequest {
            request_type: "run".to_string(),
            timestamp,
            timeout_ms: STRATEGY_RUN_TIMEOUT_MS,
            trader_data: trader_data.clone(),
            order_depths,
            own_trades: fills_to_worker_trade_map(&prev_own_trades, product_names),
            market_trades: fills_to_worker_trade_map(&prev_market_trades, product_names),
            position,
        };
        let response = worker.run(&request)?;
        trader_data = response.trader_data.unwrap_or_default();

        let mut live_books: HashMap<String, SimBook> = sampled_products
            .iter()
            .enumerate()
            .map(|(i, s)| (s.name.clone(), book_to_sim_book(&books[i])))
            .collect();

        let strategy_orders = normalize_strategy_orders(
            response.orders.unwrap_or_default(),
            product_names,
        );
        let filtered_orders = enforce_strategy_limits(&strategy_orders, &ledgers, sampled_products);

        let mut own_trades_this_tick: HashMap<String, Vec<Fill>> = empty_trade_map(product_names);
        let mut market_trades_this_tick: HashMap<String, Vec<Fill>> = empty_trade_map(product_names);

        for sampled in sampled_products {
            let product_key = &sampled.name;
            let orders = filtered_orders
                .get(product_key)
                .cloned()
                .unwrap_or_default();
            let book = live_books.get_mut(product_key).context("missing live book")?;
            let ledger = ledgers.get_mut(product_key).context("missing ledger")?;
            let fills = execute_strategy_orders(product_key, timestamp, book, ledger, &orders);
            if capture_outputs {
                trade_rows.extend(fills.iter().map(fill_to_trade_row));
            }
            own_trades_this_tick.insert(product_key.clone(), fills);
        }

        for (idx, sampled) in sampled_products.iter().enumerate() {
            let product_key = &sampled.name;
            let count = trade_counts_per_product[idx][tick];
            let book = live_books.get_mut(product_key).context("missing live book for taker")?;
            let ledger = ledgers.get_mut(product_key).context("missing ledger for taker")?;
            for _ in 0..count {
                let market_buy = sample_trade_side(sampled, rng);
                let fills = execute_taker_trade(product_key, timestamp, book, ledger, market_buy, rng);
                for fill in fills {
                    let row = fill_to_trade_row(&fill);
                    if fill_involves_strategy(&fill) {
                        own_trades_this_tick.entry(product_key.clone()).or_default().push(fill);
                    } else {
                        market_trades_this_tick.entry(product_key.clone()).or_default().push(fill);
                    }
                    if capture_outputs {
                        trade_rows.push(row);
                    }
                }
            }
        }

        if capture_outputs {
            for (i, sampled) in sampled_products.iter().enumerate() {
                let product_key = &sampled.name;
                let ledger = ledgers.get(product_key).context("missing ledger for trace")?;
                let fair = if sampled.name == "TOMATOES" {
                    tomato_fair[tick]
                } else {
                    fv_states[i].current
                };
                trace_rows.push(TraceRow {
                    day,
                    timestamp,
                    product: product_key.clone(),
                    fair_value: fair,
                    position: ledger.position,
                    cash: ledger.cash,
                    mtm_pnl: ledger.cash + ledger.position as f64 * fair,
                });
            }
        }

        let day_x = day_step as f64;
        let mut day_total_mtm = 0.0;
        for (i, sampled) in sampled_products.iter().enumerate() {
            let product_key = &sampled.name;
            let ledger = ledgers.get(product_key).context("missing ledger for fit")?;
            let fair = if sampled.name == "TOMATOES" {
                tomato_fair[tick]
            } else {
                fv_states[i].current
            };
            let mtm = ledger.cash + ledger.position as f64 * fair;
            day_total_mtm += mtm;
            day_product_fits.get_mut(product_key).context("missing day product fit")?.update(day_x, mtm);
        }
        day_total_fit.update(day_x, day_total_mtm);
        day_step += 1;

        prev_own_trades = own_trades_this_tick;
        prev_market_trades = market_trades_this_tick;
    }

    // compute final per-product PnL
    let mut per_product_pnl: HashMap<String, f64> = HashMap::new();
    let mut per_product_cash: HashMap<String, f64> = HashMap::new();
    let mut per_product_position: HashMap<String, i32> = HashMap::new();
    for (i, sampled) in sampled_products.iter().enumerate() {
        let product_key = &sampled.name;
        let ledger = ledgers.get(product_key).context("missing ledger for day pnl")?;
        let fair = if sampled.name == "TOMATOES" {
            tomato_fair.last().copied().unwrap_or(5000.0)
        } else {
            fv_states[i].current
        };
        let pnl = ledger.cash + ledger.position as f64 * fair;
        per_product_pnl.insert(product_key.clone(), pnl);
        per_product_cash.insert(product_key.clone(), ledger.cash);
        per_product_position.insert(product_key.clone(), ledger.position);
    }

    Ok(DaySimResult {
        per_product_pnl,
        per_product_cash,
        per_product_position,
        day_output: DayOutput { day, price_rows, trade_rows, trace_rows },
        day_total_fit,
        day_product_fits,
    })
}

fn run_backtest_session(
    session_id: usize,
    capture_outputs: bool,
    config: &Config,
    replay: &ReplayData,
) -> Result<SessionOutput> {
    let mut worker = StrategyWorker::spawn(config)?;
    let mut day_outputs = Vec::with_capacity(1);
    let mut total_fit = RunningLinearFit::default();
    let mut run_summaries = Vec::with_capacity(1);
    let session_day = monte_carlo_session_day(session_id);

    let product_names: Vec<String> = config.sim_config.products.iter().map(|p| p.name.clone()).collect();
    let mut session_pnl: HashMap<String, f64> = product_names.iter().map(|n| (n.clone(), 0.0)).collect();
    let mut session_cash: HashMap<String, f64> = product_names.iter().map(|n| (n.clone(), 0.0)).collect();
    let mut session_position: HashMap<String, i32> = product_names.iter().map(|n| (n.clone(), 0)).collect();
    let mut product_fits: HashMap<String, RunningLinearFit> = product_names.iter().map(|n| (n.clone(), RunningLinearFit::default())).collect();

    for day in [session_day] {
        // rng: first samples params (preserving original determinism), then drives the tick sim
        let mut rng = ChaCha8Rng::seed_from_u64(seed_for_session_day(config.seed, session_id, day));
        let nominal_sampled: Vec<config::SampledProductParams> = config
            .sim_config
            .products
            .iter()
            .map(|pc| {
                if config.fixed_params {
                    pc.to_point_estimate()
                } else {
                    pc.sample_from_posterior(&mut rng)
                }
            })
            .collect();

        let result = simulate_day(
            &mut worker,
            &nominal_sampled,
            &product_names,
            config,
            replay,
            day,
            &mut rng,
            capture_outputs,
        )?;

        // update session accumulators
        for (product_key, pnl) in &result.per_product_pnl {
            *session_pnl.entry(product_key.clone()).or_insert(0.0) += pnl;
        }
        for (product_key, cash) in &result.per_product_cash {
            *session_cash.entry(product_key.clone()).or_insert(0.0) += cash;
        }
        for (product_key, pos) in &result.per_product_position {
            *session_position.entry(product_key.clone()).or_insert(0) = *pos;
        }

        // since there is exactly one day per session, day fits == session fits
        for n in &product_names {
            if let Some(df) = result.day_product_fits.get(n) {
                if let Some(pf) = product_fits.get_mut(n) {
                    *pf = df.clone();
                }
            }
        }
        total_fit = result.day_total_fit.clone();

        let day_total_pnl: f64 = result.per_product_pnl.values().sum();
        let day_per_product_slope: HashMap<String, f64> = product_names.iter()
            .map(|n| (n.clone(), result.day_product_fits.get(n).map(|f| f.slope_per_step()).unwrap_or(0.0)))
            .collect();
        let day_per_product_r2: HashMap<String, f64> = product_names.iter()
            .map(|n| (n.clone(), result.day_product_fits.get(n).map(|f| f.r_squared()).unwrap_or(0.0)))
            .collect();

        run_summaries.push(RunSummary {
            session_id,
            day,
            total_pnl: day_total_pnl,
            per_product_pnl: result.per_product_pnl.clone(),
            total_slope_per_step: result.day_total_fit.slope_per_step(),
            total_r2: result.day_total_fit.r_squared(),
            per_product_slope_per_step: day_per_product_slope,
            per_product_r2: day_per_product_r2,
        });

        day_outputs.push(result.day_output);
    }

    let total_pnl: f64 = session_pnl.values().sum();
    let per_product_slope_per_step: HashMap<String, f64> = product_names.iter()
        .map(|n| (n.clone(), product_fits.get(n).map(|f| f.slope_per_step()).unwrap_or(0.0)))
        .collect();
    let per_product_r2: HashMap<String, f64> = product_names.iter()
        .map(|n| (n.clone(), product_fits.get(n).map(|f| f.r_squared()).unwrap_or(0.0)))
        .collect();

    let summary = SessionSummary {
        session_id,
        total_pnl,
        per_product_pnl: session_pnl.clone(),
        per_product_position: session_position,
        per_product_cash: session_cash,
        per_product_slope_per_step,
        per_product_r2,
        total_slope_per_step: total_fit.slope_per_step(),
        total_r2: total_fit.r_squared(),
    };

    // DRO: run K adversarial simulations if enabled
    let dro_session_report = if config.dro {
        let nominal_total_pnl = total_pnl;
        let per_product_nominal_pnl = session_pnl.clone();

        let mut adv_rng = ChaCha8Rng::seed_from_u64(
            seed_for_session_day(config.seed, session_id, session_day).wrapping_add(0xD4_0000_0000u64)
        );
        let adv_batches = dro::sample_adversarial_params(
            &config.sim_config.products,
            config.dro_radius,
            config.dro_k,
            &mut adv_rng,
        );

        let mut worst_per_product: HashMap<String, f64> = per_product_nominal_pnl
            .iter()
            .map(|(k, _)| (k.clone(), f64::INFINITY))
            .collect();
        let mut worst_total = f64::INFINITY;

        for (adv_idx, adv_params) in adv_batches.iter().enumerate() {
            let mut adv_rng2 = ChaCha8Rng::seed_from_u64(
                seed_for_session_day(config.seed, session_id, session_day)
                    .wrapping_add(0xD4_0000_0000u64)
                    .wrapping_add(adv_idx as u64 + 1)
            );
            let adv_result = simulate_day(
                &mut worker,
                adv_params,
                &product_names,
                config,
                replay,
                session_day,
                &mut adv_rng2,
                false,
            )?;
            let adv_total: f64 = adv_result.per_product_pnl.values().sum();
            if adv_total < worst_total {
                worst_total = adv_total;
            }
            for (k, v) in &adv_result.per_product_pnl {
                let entry = worst_per_product.entry(k.clone()).or_insert(f64::INFINITY);
                if *v < *entry {
                    *entry = *v;
                }
            }
        }
        // if no adversarial draws produced finite values, fall back to nominal
        if worst_total == f64::INFINITY {
            worst_total = nominal_total_pnl;
        }
        for (k, v) in worst_per_product.iter_mut() {
            if *v == f64::INFINITY {
                *v = *per_product_nominal_pnl.get(k).unwrap_or(&0.0);
            }
        }

        Some(dro::DroSessionReport {
            session_id,
            nominal_total_pnl,
            worst_total_pnl: worst_total,
            per_product_nominal_pnl,
            per_product_worst_pnl: worst_per_product,
        })
    } else {
        None
    };

    Ok(SessionOutput {
        session_id,
        summary,
        run_summaries,
        day_outputs,
        dro_session_report,
    })
}

/// Build CSV header for session summary (sorted by product name for stability).
fn session_summary_header(product_names: &[String]) -> Vec<String> {
    let mut sorted: Vec<&String> = product_names.iter().collect();
    sorted.sort();
    let mut cols = vec!["session_id".to_string(), "total_pnl".to_string()];
    for n in &sorted {
        cols.push(format!("{}_pnl", n));
    }
    for n in &sorted {
        cols.push(format!("{}_position", n));
    }
    for n in &sorted {
        cols.push(format!("{}_cash", n));
    }
    cols.push("total_slope_per_step".to_string());
    cols.push("total_r2".to_string());
    for n in &sorted {
        cols.push(format!("{}_slope_per_step", n));
    }
    for n in &sorted {
        cols.push(format!("{}_r2", n));
    }
    cols
}

fn session_summary_row(summary: &SessionSummary, product_names: &[String]) -> Vec<String> {
    let mut sorted: Vec<&String> = product_names.iter().collect();
    sorted.sort();
    let mut row = vec![
        summary.session_id.to_string(),
        summary.total_pnl.to_string(),
    ];
    for n in &sorted {
        row.push(summary.per_product_pnl.get(*n).copied().unwrap_or(0.0).to_string());
    }
    for n in &sorted {
        row.push(summary.per_product_position.get(*n).copied().unwrap_or(0).to_string());
    }
    for n in &sorted {
        row.push(summary.per_product_cash.get(*n).copied().unwrap_or(0.0).to_string());
    }
    row.push(summary.total_slope_per_step.to_string());
    row.push(summary.total_r2.to_string());
    for n in &sorted {
        row.push(summary.per_product_slope_per_step.get(*n).copied().unwrap_or(0.0).to_string());
    }
    for n in &sorted {
        row.push(summary.per_product_r2.get(*n).copied().unwrap_or(0.0).to_string());
    }
    row
}

fn run_summary_header(product_names: &[String]) -> Vec<String> {
    let mut sorted: Vec<&String> = product_names.iter().collect();
    sorted.sort();
    let mut cols = vec!["session_id".to_string(), "day".to_string(), "total_pnl".to_string()];
    for n in &sorted {
        cols.push(format!("{}_pnl", n));
    }
    cols.push("total_slope_per_step".to_string());
    cols.push("total_r2".to_string());
    for n in &sorted {
        cols.push(format!("{}_slope_per_step", n));
    }
    for n in &sorted {
        cols.push(format!("{}_r2", n));
    }
    cols
}

fn run_summary_row(rs: &RunSummary, product_names: &[String]) -> Vec<String> {
    let mut sorted: Vec<&String> = product_names.iter().collect();
    sorted.sort();
    let mut row = vec![
        rs.session_id.to_string(),
        rs.day.to_string(),
        rs.total_pnl.to_string(),
    ];
    for n in &sorted {
        row.push(rs.per_product_pnl.get(*n).copied().unwrap_or(0.0).to_string());
    }
    row.push(rs.total_slope_per_step.to_string());
    row.push(rs.total_r2.to_string());
    for n in &sorted {
        row.push(rs.per_product_slope_per_step.get(*n).copied().unwrap_or(0.0).to_string());
    }
    for n in &sorted {
        row.push(rs.per_product_r2.get(*n).copied().unwrap_or(0.0).to_string());
    }
    row
}

fn write_backtest_outputs(config: &Config, outputs: &[SessionOutput]) -> Result<()> {
    fs::create_dir_all(&config.output_dir)?;

    let product_names: Vec<String> = config.sim_config.products.iter().map(|p| p.name.clone()).collect();

    let summary_path = config.output_dir.join("session_summary.csv");
    let mut writer = WriterBuilder::new()
        .delimiter(b',')
        .from_path(&summary_path)
        .with_context(|| format!("failed to open {}", summary_path.display()))?;
    writer.write_record(session_summary_header(&product_names))?;
    for output in outputs {
        writer.write_record(session_summary_row(&output.summary, &product_names))?;
    }
    writer.flush()?;

    let run_summary_path = config.output_dir.join("run_summary.csv");
    let mut run_writer = WriterBuilder::new()
        .delimiter(b',')
        .from_path(&run_summary_path)
        .with_context(|| format!("failed to open {}", run_summary_path.display()))?;
    run_writer.write_record(run_summary_header(&product_names))?;
    for output in outputs {
        for run_summary in &output.run_summaries {
            run_writer.write_record(run_summary_row(run_summary, &product_names))?;
        }
    }
    run_writer.flush()?;

    for output in outputs.iter().take(config.write_session_limit) {
        let round_dir = config
            .output_dir
            .join("sessions")
            .join(format!("session_{:05}", output.session_id))
            .join("round0");
        fs::create_dir_all(&round_dir)?;
        for day_output in &output.day_outputs {
            let price_path = round_dir.join(format!("prices_round_0_day_{}.csv", day_output.day));
            let trade_path = round_dir.join(format!("trades_round_0_day_{}.csv", day_output.day));
            let trace_path = round_dir.join(format!("trace_round_0_day_{}.csv", day_output.day));
            let mut price_writer = WriterBuilder::new().delimiter(b';').from_path(&price_path)?;
            for row in &day_output.price_rows {
                price_writer.serialize(row)?;
            }
            price_writer.flush()?;

            let mut trade_writer = WriterBuilder::new().delimiter(b';').from_path(&trade_path)?;
            for row in &day_output.trade_rows {
                trade_writer.serialize(row)?;
            }
            trade_writer.flush()?;

            let mut trace_writer = WriterBuilder::new().delimiter(b';').from_path(&trace_path)?;
            for row in &day_output.trace_rows {
                trace_writer.serialize(row)?;
            }
            trace_writer.flush()?;
        }
    }

    Ok(())
}

fn write_dro_report(config: &Config, report: &dro::DroReport) -> Result<()> {
    fs::create_dir_all(&config.output_dir)?;
    let path = config.output_dir.join("dro_report.json");
    let json = serde_json::to_string_pretty(report)?;
    fs::write(&path, json).with_context(|| format!("failed to write {}", path.display()))?;
    Ok(())
}

fn write_run_log(config: &Config) -> Result<()> {
    let log_path = config.output_dir.join("run.log");
    let contents = format!(
        "seed={}\nfv_mode={:?}\ntrade_mode={:?}\nactual_dir={}\nstrategy={}\nsessions={}\nwrite_session_limit={}\n",
        config.seed,
        config.fv_mode,
        config.trade_mode,
        config.actual_dir.display(),
        config
            .strategy_path
            .as_ref()
            .map(|path| path.display().to_string())
            .unwrap_or_else(|| "".to_string()),
        config.sessions,
        config.write_session_limit,
    );
    fs::create_dir_all(&config.output_dir)?;
    fs::write(&log_path, contents)
        .with_context(|| format!("failed to write {}", log_path.display()))?;
    Ok(())
}

fn seed_for_day(seed: u64, day: i32) -> u64 {
    let mut value = seed ^ (day as i64 as u64).wrapping_mul(0x9E37_79B9_7F4A_7C15);
    value ^= value >> 33;
    value = value.wrapping_mul(0xFF51_AFD7_ED55_8CCD);
    value ^= value >> 33;
    value
}

fn seed_for_session_day(seed: u64, session_id: usize, day: i32) -> u64 {
    seed_for_day(seed ^ ((session_id as u64).wrapping_mul(0xA24B_AED4_963E_E407)), day)
}

fn empty_trade_map(product_names: &[String]) -> HashMap<String, Vec<Fill>> {
    product_names.iter().map(|n| (n.clone(), Vec::new())).collect()
}

fn fills_to_worker_trade_map(
    source: &HashMap<String, Vec<Fill>>,
    product_names: &[String],
) -> HashMap<String, Vec<WorkerTrade>> {
    product_names
        .iter()
        .map(|product| {
            let trades = source
                .get(product)
                .cloned()
                .unwrap_or_default()
                .into_iter()
                .map(|fill| WorkerTrade {
                    symbol: fill.symbol,
                    price: fill.price,
                    quantity: fill.quantity,
                    buyer: fill.buyer,
                    seller: fill.seller,
                    timestamp: fill.timestamp,
                })
                .collect::<Vec<_>>();
            (product.clone(), trades)
        })
        .collect()
}

fn book_to_worker_depth(book: &Book) -> WorkerOrderDepth {
    let buy_orders = book
        .bids
        .iter()
        .map(|(price, qty)| (price.to_string(), *qty))
        .collect::<HashMap<_, _>>();
    let sell_orders = book
        .asks
        .iter()
        .map(|(price, qty)| (price.to_string(), -*qty))
        .collect::<HashMap<_, _>>();
    WorkerOrderDepth {
        buy_orders,
        sell_orders,
    }
}

fn book_to_sim_book(book: &Book) -> SimBook {
    SimBook {
        bids: book
            .bids
            .iter()
            .map(|(price, quantity)| Level {
                price: *price,
                quantity: *quantity,
                owner: LevelOwner::Bot,
            })
            .collect(),
        asks: book
            .asks
            .iter()
            .map(|(price, quantity)| Level {
                price: *price,
                quantity: *quantity,
                owner: LevelOwner::Bot,
            })
            .collect(),
    }
}

fn normalize_strategy_orders(
    raw: HashMap<String, Vec<WorkerOrder>>,
    product_names: &[String],
) -> HashMap<String, Vec<WorkerOrder>> {
    product_names
        .iter()
        .map(|product| {
            (
                product.clone(),
                raw.get(product).cloned().unwrap_or_default(),
            )
        })
        .collect()
}

fn enforce_strategy_limits(
    orders: &HashMap<String, Vec<WorkerOrder>>,
    ledgers: &HashMap<String, ProductLedger>,
    sampled_products: &[config::SampledProductParams],
) -> HashMap<String, Vec<WorkerOrder>> {
    orders
        .iter()
        .map(|(product, product_orders)| {
            let position_limit = sampled_products
                .iter()
                .find(|s| &s.name == product)
                .map(|s| s.position_limit)
                .unwrap_or(80);
            let current_position = ledgers.get(product).map(|ledger| ledger.position).unwrap_or(0);
            let total_buy: i32 = product_orders
                .iter()
                .filter(|order| order.quantity > 0)
                .map(|order| order.quantity)
                .sum();
            let total_sell: i32 = product_orders
                .iter()
                .filter(|order| order.quantity < 0)
                .map(|order| -order.quantity)
                .sum();

            let accepted = if current_position + total_buy > position_limit
                || current_position - total_sell < -position_limit
            {
                Vec::new()
            } else {
                product_orders.clone()
            };

            (product.clone(), accepted)
        })
        .collect()
}

fn execute_strategy_orders(
    product: &str,
    timestamp: i32,
    book: &mut SimBook,
    ledger: &mut ProductLedger,
    orders: &[WorkerOrder],
) -> Vec<Fill> {
    let mut fills = Vec::new();
    let mut passive_bids: HashMap<i32, i32> = HashMap::new();
    let mut passive_asks: HashMap<i32, i32> = HashMap::new();

    for order in orders {
        if order.quantity > 0 {
            let mut remaining = order.quantity;
            while remaining > 0 {
                let Some(best_ask) = book.asks.first_mut() else {
                    break;
                };
                if best_ask.owner != LevelOwner::Bot || best_ask.price > order.price {
                    break;
                }
                let fill_qty = remaining.min(best_ask.quantity);
                fills.push(Fill {
                    symbol: product.to_string(),
                    price: best_ask.price,
                    quantity: fill_qty,
                    buyer: Some("SUBMISSION".to_string()),
                    seller: Some("BOT".to_string()),
                    timestamp,
                });
                ledger.position += fill_qty;
                ledger.cash -= best_ask.price as f64 * fill_qty as f64;
                remaining -= fill_qty;
                best_ask.quantity -= fill_qty;
                if best_ask.quantity == 0 {
                    book.asks.remove(0);
                }
            }
            if remaining > 0 {
                *passive_bids.entry(order.price).or_insert(0) += remaining;
            }
        } else if order.quantity < 0 {
            let mut remaining = -order.quantity;
            while remaining > 0 {
                let Some(best_bid) = book.bids.first_mut() else {
                    break;
                };
                if best_bid.owner != LevelOwner::Bot || best_bid.price < order.price {
                    break;
                }
                let fill_qty = remaining.min(best_bid.quantity);
                fills.push(Fill {
                    symbol: product.to_string(),
                    price: best_bid.price,
                    quantity: fill_qty,
                    buyer: Some("BOT".to_string()),
                    seller: Some("SUBMISSION".to_string()),
                    timestamp,
                });
                ledger.position -= fill_qty;
                ledger.cash += best_bid.price as f64 * fill_qty as f64;
                remaining -= fill_qty;
                best_bid.quantity -= fill_qty;
                if best_bid.quantity == 0 {
                    book.bids.remove(0);
                }
            }
            if remaining > 0 {
                *passive_asks.entry(order.price).or_insert(0) += remaining;
            }
        }
    }

    for (price, quantity) in passive_bids {
        insert_level(
            &mut book.bids,
            Level {
                price,
                quantity,
                owner: LevelOwner::Strategy,
            },
            true,
        );
    }
    for (price, quantity) in passive_asks {
        insert_level(
            &mut book.asks,
            Level {
                price,
                quantity,
                owner: LevelOwner::Strategy,
            },
            false,
        );
    }

    fills
}

fn execute_taker_trade(
    product: &str,
    timestamp: i32,
    book: &mut SimBook,
    ledger: &mut ProductLedger,
    market_buy: bool,
    rng: &mut ChaCha8Rng,
) -> Vec<Fill> {
    let mut fills = Vec::new();
    let available_volume = if market_buy {
        book.asks.iter().map(|level| level.quantity).sum()
    } else {
        book.bids.iter().map(|level| level.quantity).sum()
    };
    if available_volume <= 0 {
        return fills;
    }

    let mut remaining = sample_trade_quantity_by_side(product, market_buy, available_volume, rng);

    while remaining > 0 {
        let (price, owner, fill_qty) = if market_buy {
            let Some(best_ask) = book.asks.first_mut() else {
                break;
            };
            let fill_qty = remaining.min(best_ask.quantity);
            let price = best_ask.price;
            let owner = best_ask.owner;
            best_ask.quantity -= fill_qty;
            if best_ask.quantity == 0 {
                book.asks.remove(0);
            }
            (price, owner, fill_qty)
        } else {
            let Some(best_bid) = book.bids.first_mut() else {
                break;
            };
            let fill_qty = remaining.min(best_bid.quantity);
            let price = best_bid.price;
            let owner = best_bid.owner;
            best_bid.quantity -= fill_qty;
            if best_bid.quantity == 0 {
                book.bids.remove(0);
            }
            (price, owner, fill_qty)
        };

        if fill_qty <= 0 {
            break;
        }

        let fill = match (market_buy, owner) {
            (true, LevelOwner::Bot) => Fill {
                symbol: product.to_string(),
                price,
                quantity: fill_qty,
                buyer: Some("BOT_TAKER".to_string()),
                seller: Some("BOT_MAKER".to_string()),
                timestamp,
            },
            (true, LevelOwner::Strategy) => {
                ledger.position -= fill_qty;
                ledger.cash += price as f64 * fill_qty as f64;
                Fill {
                    symbol: product.to_string(),
                    price,
                    quantity: fill_qty,
                    buyer: Some("BOT_TAKER".to_string()),
                    seller: Some("SUBMISSION".to_string()),
                    timestamp,
                }
            }
            (false, LevelOwner::Bot) => Fill {
                symbol: product.to_string(),
                price,
                quantity: fill_qty,
                buyer: Some("BOT_MAKER".to_string()),
                seller: Some("BOT_TAKER".to_string()),
                timestamp,
            },
            (false, LevelOwner::Strategy) => {
                ledger.position += fill_qty;
                ledger.cash -= price as f64 * fill_qty as f64;
                Fill {
                    symbol: product.to_string(),
                    price,
                    quantity: fill_qty,
                    buyer: Some("SUBMISSION".to_string()),
                    seller: Some("BOT_TAKER".to_string()),
                    timestamp,
                }
            }
        };
        fills.push(fill);
        remaining -= fill_qty;
    }

    fills
}

fn insert_level(levels: &mut Vec<Level>, level: Level, descending: bool) {
    if let Some(existing) = levels
        .iter_mut()
        .find(|existing| existing.price == level.price && existing.owner == level.owner)
    {
        existing.quantity += level.quantity;
    } else {
        levels.push(level);
    }
    if descending {
        levels.sort_by(|a, b| b.price.cmp(&a.price).then(owner_priority(a.owner).cmp(&owner_priority(b.owner))));
    } else {
        levels.sort_by(|a, b| a.price.cmp(&b.price).then(owner_priority(a.owner).cmp(&owner_priority(b.owner))));
    }
}

fn owner_priority(owner: LevelOwner) -> i32 {
    match owner {
        LevelOwner::Bot => 0,
        LevelOwner::Strategy => 1,
    }
}

fn fill_involves_strategy(fill: &Fill) -> bool {
    fill.buyer.as_deref() == Some("SUBMISSION") || fill.seller.as_deref() == Some("SUBMISSION")
}

fn fill_to_trade_row(fill: &Fill) -> TradeRow {
    TradeRow {
        timestamp: fill.timestamp,
        buyer: fill.buyer.clone(),
        seller: fill.seller.clone(),
        symbol: fill.symbol.clone(),
        currency: "XIRECS".to_string(),
        price: fill.price as f64,
        quantity: fill.quantity,
    }
}

fn sample_trade_side(sampled: &config::SampledProductParams, rng: &mut ChaCha8Rng) -> bool {
    rng.r#gen::<f64>() < sampled.taker_buy_prob
}

fn load_price_rows(actual_dir: &Path, day: i32) -> Result<Vec<InputPriceRow>> {
    let path = actual_dir.join(format!("prices_round_0_day_{}.csv", day));
    let mut reader = ReaderBuilder::new()
        .delimiter(b';')
        .from_path(&path)
        .with_context(|| format!("failed to read {}", path.display()))?;
    let mut rows = Vec::new();
    for record in reader.deserialize() {
        let row: InputPriceRow = record?;
        rows.push(row);
    }
    Ok(rows)
}

fn load_trade_rows(actual_dir: &Path, day: i32) -> Result<Vec<InputTradeRow>> {
    let path = actual_dir.join(format!("trades_round_0_day_{}.csv", day));
    let mut reader = ReaderBuilder::new()
        .delimiter(b';')
        .from_path(&path)
        .with_context(|| format!("failed to read {}", path.display()))?;
    let mut rows = Vec::new();
    for record in reader.deserialize() {
        let row: InputTradeRow = record?;
        rows.push(row);
    }
    Ok(rows)
}

fn infer_observed_fair(row: &InputPriceRow) -> f64 {
    let bids = [row.bid_price_1, row.bid_price_2, row.bid_price_3]
        .into_iter()
        .flatten()
        .collect::<Vec<_>>();
    let asks = [row.ask_price_1, row.ask_price_2, row.ask_price_3]
        .into_iter()
        .flatten()
        .collect::<Vec<_>>();
    let worst_bid = bids.into_iter().min().unwrap_or(0);
    let worst_ask = asks.into_iter().max().unwrap_or(0);
    (worst_bid as f64 + worst_ask as f64) / 2.0
}

fn estimate_tomato_fair(row: &InputPriceRow) -> f64 {
    let Some((inner_bid, outer_bid, inner_ask, outer_ask)) = tomato_wall_quotes(row) else {
        return infer_observed_fair(row);
    };

    let intervals = [
        interval_from_quote(outer_bid, -8.0),
        interval_from_quote(outer_ask, 8.0),
        interval_from_quote(inner_bid, -6.5),
        interval_from_quote(inner_ask, 6.5),
    ];

    let lower = intervals
        .iter()
        .map(|(lo, _)| *lo)
        .fold(f64::NEG_INFINITY, f64::max);
    let upper = intervals
        .iter()
        .map(|(_, hi)| *hi)
        .fold(f64::INFINITY, f64::min);

    if lower <= upper {
        (lower + upper) / 2.0
    } else {
        (outer_bid as f64 + outer_ask as f64) / 2.0
    }
}

fn tomato_wall_quotes(row: &InputPriceRow) -> Option<(i32, i32, i32, i32)> {
    let bid3 = row.bid_price_3.is_some();
    let ask3 = row.ask_price_3.is_some();

    match (bid3, ask3) {
        (false, false) => Some((
            row.bid_price_1?,
            row.bid_price_2?,
            row.ask_price_1?,
            row.ask_price_2?,
        )),
        (true, false) => Some((
            row.bid_price_2?,
            row.bid_price_3?,
            row.ask_price_1?,
            row.ask_price_2?,
        )),
        (false, true) => Some((
            row.bid_price_1?,
            row.bid_price_2?,
            row.ask_price_2?,
            row.ask_price_3?,
        )),
        (true, true) => None,
    }
}

fn interval_from_quote(price: i32, offset: f64) -> (f64, f64) {
    (
        price as f64 - 0.5 - offset,
        price as f64 + 0.5 - offset,
    )
}

fn trade_counts_for(
    sampled: &config::SampledProductParams,
    day: i32,
    config: &Config,
    replay: &ReplayData,
    rng: &mut ChaCha8Rng,
) -> Result<Vec<usize>> {
    match config.trade_mode {
        TradeMode::ReplayTimes => replay
            .trade_counts_by_key
            .get(&(day, sampled.name.clone()))
            .cloned()
            .context("missing replay trade count series"),
        TradeMode::Simulate => Ok(simulate_trade_counts(sampled, config.ticks_per_day, rng)),
    }
}

fn simulate_trade_counts(sampled: &config::SampledProductParams, ticks: usize, rng: &mut ChaCha8Rng) -> Vec<usize> {
    let base_prob = sampled.taker_trade_active_prob;
    let second_trade_prob = sampled.taker_second_trade_prob;
    let mut counts = vec![0usize; ticks];
    for count in &mut counts {
        if rng.gen_bool(base_prob.clamp(f64::EPSILON, 1.0 - f64::EPSILON)) {
            *count = 1;
            if second_trade_prob > 0.0 && rng.gen_bool(second_trade_prob.clamp(f64::EPSILON, 1.0 - f64::EPSILON)) {
                *count += 1;
            }
        }
    }
    counts
}

fn simulate_tomato_fair_series(day: i32, ticks: usize, rng: &mut ChaCha8Rng) -> Vec<f64> {
    let start: f64 = if day == -1 { 5006.0 } else { 5000.0 };
    let sigma = 0.496;
    let mut series = vec![0.0f64; ticks];
    series[0] = start.round();
    for index in 1..ticks {
        let u1 = rng.gen_range(f64::EPSILON..1.0);
        let u2 = rng.gen_range(0.0..1.0);
        let step = sigma * (-2.0 * u1.ln()).sqrt() * (2.0 * std::f64::consts::PI * u2).cos();
        series[index] = (series[index - 1] + step).round();
    }
    series
}

/// Generic book builder driven by `SampledProductParams`.
/// bot1 = outer market maker, bot2 = inner market maker.
fn make_book(sampled: &config::SampledProductParams, fv: f64, rng: &mut ChaCha8Rng) -> Book {
    let bot1_vol = rng.gen_range(sampled.bot1_volume_lo..=sampled.bot1_volume_hi) as i32;
    let bot2_vol = rng.gen_range(sampled.bot2_volume_lo..=sampled.bot2_volume_hi) as i32;

    let (outer_bid, outer_ask) = products::quote_for_rule(
        &sampled.bot1_bid_rule,
        &sampled.bot1_ask_rule,
        fv,
        sampled.bot1_offset,
    );
    let (inner_bid, inner_ask) = products::quote_for_rule(
        &sampled.bot2_bid_rule,
        &sampled.bot2_ask_rule,
        fv,
        sampled.bot2_offset,
    );

    // bot3 presence check
    let draw: f64 = rng.r#gen();
    if draw < sampled.bot3_presence * sampled.bot3_side_bid_prob {
        // bot3 on bid side
        let (bot3_price, bot3_vol) = sample_bot3_quote(fv, sampled, true, rng);
        Book {
            bids: vec![
                (bot3_price, bot3_vol),
                (inner_bid, bot2_vol),
                (outer_bid, bot1_vol),
            ],
            asks: vec![(inner_ask, bot2_vol), (outer_ask, bot1_vol)],
        }
    } else if draw < sampled.bot3_presence {
        // bot3 on ask side
        let (bot3_price, bot3_vol) = sample_bot3_quote(fv, sampled, false, rng);
        Book {
            bids: vec![(inner_bid, bot2_vol), (outer_bid, bot1_vol)],
            asks: vec![
                (bot3_price, bot3_vol),
                (inner_ask, bot2_vol),
                (outer_ask, bot1_vol),
            ],
        }
    } else {
        Book {
            bids: vec![(inner_bid, bot2_vol), (outer_bid, bot1_vol)],
            asks: vec![(inner_ask, bot2_vol), (outer_ask, bot1_vol)],
        }
    }
}

fn sample_bot3_quote(
    fv: f64,
    sampled: &config::SampledProductParams,
    is_bid: bool,
    rng: &mut ChaCha8Rng,
) -> (i32, i32) {
    let support = &sampled.bot3_price_delta_support;
    let delta = if support.is_empty() {
        0
    } else {
        support[rng.gen_range(0..support.len())]
    };
    // for bid, aggressive = positive delta; for ask, aggressive = negative delta
    let price = fv.round() as i32 + if is_bid { delta } else { -delta };
    // determine if this delta is "crossing" (aggressive) or passive
    // crossing: delta causes bot to cross the spread (bid delta > 0 or ask delta > 0 after negation)
    let is_crossing = if is_bid { delta > 0 } else { delta < 0 };
    let vol = if is_crossing {
        rng.gen_range(sampled.bot3_crossing_volume_lo..=sampled.bot3_crossing_volume_hi) as i32
    } else {
        rng.gen_range(sampled.bot3_passive_volume_lo..=sampled.bot3_passive_volume_hi) as i32
    };
    (price, vol)
}

fn book_to_price_row(day: i32, timestamp: i32, product: &str, book: &Book) -> PriceRow {
    let bid1 = book.bids.first().copied();
    let bid2 = book.bids.get(1).copied();
    let bid3 = book.bids.get(2).copied();
    let ask1 = book.asks.first().copied();
    let ask2 = book.asks.get(1).copied();
    let ask3 = book.asks.get(2).copied();
    let mid_price = (book.bids[0].0 as f64 + book.asks[0].0 as f64) / 2.0;

    PriceRow {
        day,
        timestamp,
        product: product.to_string(),
        bid_price_1: bid1.map(|x| x.0),
        bid_volume_1: bid1.map(|x| x.1),
        bid_price_2: bid2.map(|x| x.0),
        bid_volume_2: bid2.map(|x| x.1),
        bid_price_3: bid3.map(|x| x.0),
        bid_volume_3: bid3.map(|x| x.1),
        ask_price_1: ask1.map(|x| x.0),
        ask_volume_1: ask1.map(|x| x.1),
        ask_price_2: ask2.map(|x| x.0),
        ask_volume_2: ask2.map(|x| x.1),
        ask_price_3: ask3.map(|x| x.0),
        ask_volume_3: ask3.map(|x| x.1),
        mid_price,
        profit_and_loss: 0.0,
    }
}

fn sample_trade_rows(
    timestamp: i32,
    sampled: &config::SampledProductParams,
    book: &Book,
    rng: &mut ChaCha8Rng,
) -> Vec<TradeRow> {
    let market_buy = sample_trade_side(sampled, rng);
    let available_volume: i32 = if market_buy {
        book.asks.iter().map(|(_, volume)| *volume).sum()
    } else {
        book.bids.iter().map(|(_, volume)| *volume).sum()
    };
    if available_volume <= 0 {
        return Vec::new();
    }

    let quantity = sample_trade_quantity_by_side(&sampled.name, market_buy, available_volume, rng);

    let mut rows = Vec::new();
    let mut remaining = quantity;
    if market_buy {
        for (price, volume_limit) in &book.asks {
            if remaining <= 0 {
                break;
            }
            let fill_qty = remaining.min(*volume_limit);
            rows.push(TradeRow {
                timestamp,
                buyer: None,
                seller: None,
                symbol: sampled.name.clone(),
                currency: "XIRECS".to_string(),
                price: *price as f64,
                quantity: fill_qty,
            });
            remaining -= fill_qty;
        }
    } else {
        for (price, volume_limit) in &book.bids {
            if remaining <= 0 {
                break;
            }
            let fill_qty = remaining.min(*volume_limit);
            rows.push(TradeRow {
                timestamp,
                buyer: None,
                seller: None,
                symbol: sampled.name.clone(),
                currency: "XIRECS".to_string(),
                price: *price as f64,
                quantity: fill_qty,
            });
            remaining -= fill_qty;
        }
    }

    rows
}

fn sample_trade_quantity_by_side(
    product: &str,
    market_buy: bool,
    volume_limit: i32,
    rng: &mut ChaCha8Rng,
) -> i32 {
    let (values, weights): (&[i32], &[u32]) = match (product, market_buy) {
        ("EMERALDS", true) => (&[3, 4, 5, 6, 7, 8], &[32, 30, 34, 36, 29, 34]),
        ("EMERALDS", false) => (&[3, 4, 5, 6, 7, 8], &[28, 33, 40, 49, 30, 24]),
        ("TOMATOES", true) => (&[2, 3, 4, 5, 6], &[99, 85, 101, 100, 2]),
        ("TOMATOES", false) => (&[2, 3, 4, 5], &[110, 125, 101, 97]),
        _ => (&[1], &[1]),
    };

    let filtered = values
        .iter()
        .zip(weights.iter())
        .filter(|(value, _)| **value <= volume_limit)
        .map(|(value, weight)| (*value, *weight))
        .collect::<Vec<_>>();

    if filtered.is_empty() {
        return volume_limit.max(1);
    }

    let filtered_values = filtered.iter().map(|(value, _)| *value).collect::<Vec<_>>();
    let filtered_weights = filtered
        .iter()
        .map(|(_, weight)| *weight)
        .collect::<Vec<_>>();
    let chooser = WeightedIndex::new(filtered_weights).expect("valid filtered trade weights");
    filtered_values[chooser.sample(rng)]
}
