# Run the current version in VS Code

Open the whole extracted `campmate_app` folder. Install Python 3.12 and Node.js
22.12+ first. In its terminal run `py -3.12 scripts/setup.py`.

Configure your own `.env.llm.local` using `config/campus_llm.example` and connect
to campus/VPN. Then run:

```powershell
$env:ELEC5620_MAX_COMPLETION_TOKENS = "4096"
$env:ELEC5620_REASONING_EFFORT = "low"
.\.venv\Scripts\python.exe scripts/sydney.py --mode agent --logistics model --safety model --safety-protocol compact
```

Open http://127.0.0.1:5173. Ctrl+C stops both services. Append
`--backend-port 8001 --frontend-port 5174` if needed. Restart after backend edits.
For rules-only checks use the same Python with `scripts/sydney.py` and no flags.
On macOS/Linux use `.venv/bin/python` and `export` environment variables.

See the [README](../README.md) for accounts and the complete flow. No prefilled
user database or API key is included. For early practice of the 4 November review
example use the independent fixed-date launcher in the
[Bonnie Vale guide](demo/bonnie_vale_review_request.md). Normal `sydney.py`
intentionally uses the current date, so do not put fixed-date variables before
that launcher and expect them to be retained. Do not change the OS clock.
