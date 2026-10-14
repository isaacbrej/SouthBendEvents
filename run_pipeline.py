import os
import subprocess
import sys


def run_command(cmd, description):
    print(f"\n==========================================")
    print(f"🚀 Running: {description}")
    print(f"==========================================")
    result = subprocess.run(cmd, shell=True, text=True)
    return result.returncode == 0


def main():
    # 1. Primary Scrape Pass
    scrape_success = run_command("python main.py", "Primary Event Scraper")

    # 2. Check output & run investigator if scraper failed or produced no output
    if not scrape_success or not os.path.exists("scraped_events.json"):
        print(
            "⚠️ Scraper encountered errors or missing output. Running investigator..."
        )
        run_command("python investigate_sources.py", "Source Investigation")
        # Retry primary scrape after self-healing/diagnostics
        run_command("python main.py", "Secondary Event Scraper (Post-Repair)")

    # 3. Normalize Events
    if os.path.exists("scraped_events.json"):
        run_command("python normalize_events.py", "Event Normalization")
    else:
        print("❌ Critical Error: 'scraped_events.json' not found. Aborting.")
        sys.exit(1)

    print("\n🎉 Full pipeline completed successfully!")


if __name__ == "__main__":
    main()