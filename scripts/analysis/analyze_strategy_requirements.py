import os
import re
import json
import glob

STRATEGIES_DIR = "user_data/strategies"


def parse_strategy_timeframes(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Base Timeframe
    # Look for: timeframe = "1h" or self.timeframe = '1h'
    base_tf_match = re.search(r"timeframe\s*=\s*['\"]([^'\"]+)['\"]", content)
    base_tf = base_tf_match.group(1) if base_tf_match else "5m"  # Default fallback

    # 2. Informative Timeframes (Decorator)
    # Look for: @informative('1h')
    informative_matches = re.findall(
        r"@informative\s*\(\s*['\"]([^'\"]+)['\"]", content
    )

    # 3. Informative Pairs (Heuristic for informative.extend or explicit strings)
    # This captures common hardcoded timeframes often used in informative_pairs methods
    # e.g. "1h", '4h', etc. clearly being used as timeframes
    # We look for simple string literals that match standard timeframe patterns
    # (number + m/h/d) surrounding typical informative_pairs context or just broad search
    # Broad search is safer to avoid missing things, filters out noise later
    simple_tf_regex = r"['\"](\d+[mhdwM])['\"]"
    potential_tfs = re.findall(simple_tf_regex, content)

    # 4. Resample calls (manual MTF)
    # Look for: .resample('4h')
    resample_matches = re.findall(r"\.resample\s*\(\s*['\"]([^'\"]+)['\"]", content)

    all_tfs = {base_tf}
    all_tfs.update(informative_matches)
    all_tfs.update(resample_matches)

    # Add potentials if they look valid and aren't just random strings (though our regex is specific)
    # identifying if they are likely timeframes
    for tf in potential_tfs:
        all_tfs.add(tf)

    return list(all_tfs)


def main():
    strategy_requirements = {}

    # Get all .py files in strategies dir
    strategy_files = glob.glob(os.path.join(STRATEGIES_DIR, "*.py"))

    for strategy_file in strategy_files:
        filename = os.path.basename(strategy_file)
        if filename == "__init__.py" or "Archive" in strategy_file:
            continue

        strategy_name = filename.replace(".py", "")
        timeframes = parse_strategy_timeframes(strategy_file)

        # Normalize timeframes
        normalized_tfs = []
        for tf in timeframes:
            if tf == "D":
                normalized_tfs.append("1d")
            else:
                normalized_tfs.append(tf)

        strategy_requirements[strategy_name] = list(set(normalized_tfs))

    # Save to JSON
    with open("strategy_requirements.json", "w") as f:
        json.dump(strategy_requirements, f, indent=2)

    print(f"Analyzed {len(strategy_requirements)} strategies.")
    print("Requirements saved to strategy_requirements.json")


if __name__ == "__main__":
    main()
