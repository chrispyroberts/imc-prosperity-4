export interface UserSummary {
  id: number;
  firstName: string;
  lastName: string;
}

export interface AlgorithmSummary {
  id: string;
  content: string;
  fileName: string;
  round: string;
  selectedForRound: boolean;
  status: string;
  teamId: string;
  timestamp: string;
  graphLog: string;
  user: UserSummary;
}

export type Time = number;
export type ProsperitySymbol = string;
export type Product = string;
export type Position = number;
export type UserId = string;
export type ObservationValue = number;

export interface ActivityLogRow {
  day: number;
  timestamp: number;
  product: Product;
  bidPrices: number[];
  bidVolumes: number[];
  askPrices: number[];
  askVolumes: number[];
  midPrice: number;
  profitLoss: number;
}

export interface Listing {
  symbol: ProsperitySymbol;
  product: Product;
  denomination: Product;
}

export interface ConversionObservation {
  bidPrice: number;
  askPrice: number;
  transportFees: number;
  exportTariff: number;
  importTariff: number;
  sugarPrice: number;
  sunlightIndex: number;
}

export interface Observation {
  plainValueObservations: Record<Product, ObservationValue>;
  conversionObservations: Record<Product, ConversionObservation>;
}

export interface Order {
  symbol: ProsperitySymbol;
  price: number;
  quantity: number;
}

export interface OrderDepth {
  buyOrders: Record<number, number>;
  sellOrders: Record<number, number>;
}

export interface Trade {
  symbol: ProsperitySymbol;
  price: number;
  quantity: number;
  buyer: UserId;
  seller: UserId;
  timestamp: Time;
}

export interface TradingState {
  timestamp: Time;
  traderData: string;
  listings: Record<ProsperitySymbol, Listing>;
  orderDepths: Record<ProsperitySymbol, OrderDepth>;
  ownTrades: Record<ProsperitySymbol, Trade[]>;
  marketTrades: Record<ProsperitySymbol, Trade[]>;
  position: Record<Product, Position>;
  observations: Observation;
}

export interface AlgorithmDataRow {
  state: TradingState;
  orders: Record<ProsperitySymbol, Order[]>;
  conversions: number;
  traderData: string;
  algorithmLogs: string;
  sandboxLogs: string;
}

export interface Algorithm {
  summary?: AlgorithmSummary;
  activityLogs: ActivityLogRow[];
  data: AlgorithmDataRow[];
}

export interface MonteCarloDistributionStats {
  count: number;
  mean: number;
  std: number;
  min: number;
  p01: number;
  p05: number;
  p10: number;
  p25: number;
  p50: number;
  p75: number;
  p90: number;
  p95: number;
  p99: number;
  max: number;
  positiveRate: number;
  negativeRate: number;
  zeroRate: number;
  var95: number;
  cvar95: number;
  var99: number;
  cvar99: number;
  meanConfidenceLow95: number;
  meanConfidenceHigh95: number;
  sharpeLike: number;
  sortinoLike: number;
  skewness: number;
}

export interface MonteCarloHistogram {
  binEdges: number[];
  counts: number[];
}

export interface MonteCarloNormalFit {
  mean: number;
  std: number;
  r2: number;
  line: number[][];
}

export interface MonteCarloScatterFit {
  slope: number;
  intercept: number;
  r2: number;
  correlation: number;
  line: number[][];
  diagnosis: string;
}

export interface MonteCarloTrendFitGroup {
  profitability: MonteCarloDistributionStats;
  stability: MonteCarloDistributionStats;
}

export interface MonteCarloRunSummary {
  sessionId: number;
  day: number;
  totalPnl: number;
  emeraldPnl: number;
  tomatoPnl: number;
  totalSlopePerStep: number;
  totalR2: number;
  emeraldSlopePerStep: number;
  emeraldR2: number;
  tomatoSlopePerStep: number;
  tomatoR2: number;
}

export interface MonteCarloBandSeries {
  timestamps: number[];
  mean: number[];
  std1Low: number[];
  std1High: number[];
  std3Low: number[];
  std3High: number[];
}

export interface MonteCarloSessionSummary {
  sessionId: number;
  totalPnl: number;
  emeraldPnl: number;
  tomatoPnl: number;
  emeraldPosition: number;
  tomatoPosition: number;
  emeraldCash: number;
  tomatoCash: number;
  totalSlopePerStep: number;
  totalR2: number;
  emeraldSlopePerStep: number;
  emeraldR2: number;
  tomatoSlopePerStep: number;
  tomatoR2: number;
  runMeanTotalSlopePerStep?: number;
  runMeanTotalR2?: number;
}

export interface MonteCarloSampleProductPath {
  timestamps: number[];
  fair: number[];
  mid: number[];
  bid1: number[];
  ask1: number[];
  position: number[];
  cash: number[];
  mtmPnl: number[];
}

export interface MonteCarloSamplePath {
  sessionId: number;
  products: Record<string, MonteCarloSampleProductPath>;
  total: {
    timestamps: number[];
    mtmPnl: number[];
  };
}

export interface MonteCarloSamplePathRef {
  sessionId: number;
  url: string;
}

export interface MonteCarloStaticChartRef {
  title: string;
  url: string;
}

export interface MonteCarloGeneratorModel {
  name: string;
  formula: string;
  notes: string[];
}

export interface MonteCarloDashboard {
  kind: 'monte_carlo_dashboard';
  meta: {
    algorithmPath: string;
    sessionCount: number;
    fvMode: string;
    tradeMode: string;
    tomatoSupport: string;
    seed: number;
    sampleSessions: number;
    bandSessionCount?: number;
  };
  overall: {
    totalPnl: MonteCarloDistributionStats;
    emeraldPnl: MonteCarloDistributionStats;
    tomatoPnl: MonteCarloDistributionStats;
    emeraldTomatoCorrelation: number;
  };
  trendFits: Record<string, MonteCarloTrendFitGroup>;
  aggregateTrendFits?: Record<string, MonteCarloTrendFitGroup>;
  normalFits: {
    totalPnl: MonteCarloNormalFit;
    emeraldPnl: MonteCarloNormalFit;
    tomatoPnl: MonteCarloNormalFit;
  };
  scatterFit: MonteCarloScatterFit;
  generatorModel: Record<string, MonteCarloGeneratorModel>;
  products: Record<
    string,
    {
      pnl: MonteCarloDistributionStats;
      finalPosition: MonteCarloDistributionStats;
      cash: MonteCarloDistributionStats;
    }
  >;
  histograms: Record<string, MonteCarloHistogram>;
  sessions: MonteCarloSessionSummary[];
  runs?: MonteCarloRunSummary[];
  topSessions: MonteCarloSessionSummary[];
  bottomSessions: MonteCarloSessionSummary[];
  samplePaths: MonteCarloSamplePath[];
  samplePathRefs?: MonteCarloSamplePathRef[];
  bandChartRefs?: Record<string, MonteCarloStaticChartRef[]>;
  bandSeries?: Record<string, Record<string, MonteCarloBandSeries>>;
}

export type CompressedListing = [symbol: ProsperitySymbol, product: Product, denomination: Product];

export type CompressedOrderDepth = [buyOrders: Record<number, number>, sellOrders: Record<number, number>];

export type CompressedTrade = [
  symbol: ProsperitySymbol,
  price: number,
  quantity: number,
  buyer: UserId,
  seller: UserId,
  timestamp: Time,
];

export type CompressedConversionObservation = [
  bidPrice: number,
  askPrice: number,
  transportFees: number,
  exportTariff: number,
  importTariff: number,
  sugarPrice: number,
  sunlightIndex: number,
];

export type CompressedObservations = [
  plainValueObservations: Record<Product, ObservationValue>,
  conversionObservations: Record<Product, CompressedConversionObservation>,
];

export type CompressedTradingState = [
  timestamp: Time,
  traderData: string,
  listings: CompressedListing[],
  orderDepths: Record<ProsperitySymbol, CompressedOrderDepth>,
  ownTrades: CompressedTrade[],
  marketTrades: CompressedTrade[],
  position: Record<Product, Position>,
  observations: CompressedObservations,
];

export type CompressedOrder = [symbol: ProsperitySymbol, price: number, quantity: number];

export type CompressedAlgorithmDataRow = [
  state: CompressedTradingState,
  orders: CompressedOrder[],
  conversions: number,
  traderData: string,
  logs: string,
];
