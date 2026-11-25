"""Where the agent's data comes from.

SampleData reads the fictional files in data/. To connect real systems, write a
class with these same five methods that calls live sources instead. The README
maps each method to the DriveWealth MCP tools that return the same data.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class SampleData:
    def __init__(self, folder: Path = ROOT / "data", batch_file: Path | None = None):
        self.folder = Path(folder)
        self.batch_file = Path(batch_file) if batch_file else self.folder / "returns_batch.csv"

    def _json(self, name: str) -> dict:
        raw = json.loads((self.folder / name).read_text())
        return {k: v for k, v in raw.items() if not k.startswith("_")}

    def returned_deposits(self) -> list[dict]:
        """Today's returned ACH deposits (in production: the daily return file from the bank)."""
        with open(self.batch_file, newline="") as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            r["amount"] = float(r["amount"])
            r["addenda_info"] = (r.get("addenda_info") or "").strip()
        return rows

    def accounts(self) -> dict:
        """Brokerage accounts: partner, open date, cash, positions, bank fingerprint, past returns."""
        return self._json("accounts.json")

    def partner_volumes(self) -> dict:
        """Each partner program's ACH debits and returns over the trailing 60 days."""
        return self._json("partners.json")

    def return_codes(self) -> dict:
        """Nacha return code reference."""
        return self._json("return_codes.json")

    def handbook(self) -> str:
        """The firm's written policy. Humans read it, and the agent searches it."""
        return (ROOT / "DECISIONS.md").read_text()
