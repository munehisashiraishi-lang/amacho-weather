name: Update Amacho Weather Calendar

on:
  schedule:
    # 毎日 午前6時 と 午後6時（JST）に実行
    - cron: "0 9,21 * * *"
  workflow_dispatch:

permissions:
  contents: write

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.x"

      - name: Install dependencies
        run: |
          pip install -r requirements.txt

      - name: Generate iCal
        run: |
          python generate_ics.py

      - name: Commit and push updated calendar
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add amacho.ics
          git diff --cached --quiet || (git pull --rebase origin main && git commit -m "Update weather calendar" && git push)
