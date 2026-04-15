# additional comments from creator/repo owner (chrispyroberts)

Okay after looking at the products for this round i think i'll be able to make a mc backtester for it pretty easily
will share later.


After consideration i WONT be open sourcing the MC backtester for this round or future rounds. I have done an absurd amount of analysis today to calibrate it, and to give this to everybody is like leaking all the alpha. There is NO way for me to cleanly open source it without leaking the alpha since AI can just decode the entire thing even if its an obfuscaated binary with random memory placement ( i literally tried this and could back out my own formulas and bot logic 1:1) the only other alternative is to host this myself and people submit me algos, which is basically like saying okay everybody if u wanna test ur thingy gimme ur code hahahah trust me i wont yoink it, and if youre smart you can STILL probably figure it out by probing around in my sandbox

sorry to everybody who relied on it for preventing overfitting or was hoping i would for these rounds

i will say though - the recipe and step by step workflow for doing it is LITERALLY WRITTEN FOR YOU in .md files, with calibration stats, literal philosophies for your agents to follow and do it for you (blood sweat and tears went into those philosophy docs). its basically a recipe for finding all the alpha every round, so i encourage people to try and build their own mc sim every round since it is REALLY a powerful tool and you basically find everything there is to find when building it and getting it right.

plus its a learning experience in itself to calibrate it, i learned two VERY cool things today AND applied them
distributionally robust optimization
a certain process that fits well 🙂 just ask ur favorite agent
