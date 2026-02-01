import os
import json
import zipfile


def diagnostic_scan():
    results_dir = "user_data/backtest_results"
    files = [
        f for f in os.listdir(results_dir) if f.endswith(".zip") or f.endswith(".json")
    ]
    files.sort(
        key=lambda x: os.path.getmtime(os.path.join(results_dir, x)), reverse=True
    )

    print("Checking top 50 most recent results for ANY profit...")

    for filename in files[:50]:
        file_path = os.path.join(results_dir, filename)
        if filename.endswith(".meta.json"):
            continue

        data = None
        try:
            if filename.endswith(".json"):
                with open(file_path, "r") as f:
                    data = json.load(f)
            else:
                with zipfile.ZipFile(file_path, "r") as z:
                    for zname in z.namelist():
                        if zname.endswith(".json"):
                            with z.open(zname) as f:
                                data = json.load(f)
        except Exception:
            continue

        if data:
            strats = data.get("strategy", {})
            for sname, sdata in strats.items():
                results = sdata.get("results_per_pair", [])
                for res in results:
                    if res.get("key") == "TOTAL":
                        p = res.get("profit_total_pct", 0)
                        if p != 0:
                            print(f"{filename} | {sname} | PROFIT: {p:.2f}%")


diagnostic_scan()
