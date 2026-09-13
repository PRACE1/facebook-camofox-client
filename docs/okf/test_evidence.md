\# test evidence log



\## deterministic contract tests



\*\*Location:\*\* `tests/domain\_connectors/test\_openmagpie\_commit.py`

\*\*Type:\*\* Behavior-level connector contract (fake session for controlled input)

\*\*Count:\*\* 6 tests, all passing



These tests assert public interface behavior only. They use a `FakeSession` to supply controlled input to the connector — this is NOT live Facebook evidence.



| Test | What it proves |

|------|---------------|

| `test\_commit\_success\_advances\_cursor` | Two records committed → cursor advances to `last\_post\_id == "2"` |

| `test\_commit\_failure\_leaves\_cursor\_unchanged` | `CommitFailed` raised, cursor remains `None` |

| `test\_repeat\_poll\_deduplicates` | Second poll with same data returns empty `new\_posts` |

| `test\_output\_contains\_normalized\_post\_records` | `new\_posts` is `list\[NormalizedPostRecord]`, not `list\[dict]` |

| `test\_event\_ordering\_commit\_before\_cursor\_before\_completed\_event` | Call order: `commit` → `cursor\_save` → `posts.listen\_completed` |

| `test\_auth\_failure\_emits\_listen\_failed\_and\_leaves\_cursor` | Auth page → `posts.listen\_failed`, cursor untouched |



\*\*Command:\*\* `python -m pytest tests/domain\_connectors -q`

\*\*Result:\*\* `6 passed, 0 failed`



\## live acceptance evidence



\*\*Location:\*\* `tests/evidence/live\_posts\_listen\_acceptance.json`

\*\*Type:\*\* Real Camoufox session against live Facebook group

\*\*Date:\*\* 2026-08-21



\*\*Command run:\*\*

```powershell

$env:FACEBOOK\_GROUP\_ID = '305056891435827'

$env:FACEBOOK\_ACCOUNT\_ID = 'listen-group'

$env:CAMOFOX\_STORAGE\_STATE\_LISTEN\_GROUP = 'C:\\Users\\R5 5600 GT\\fb\_cookies\_playwright.json'

python scripts\\accept\_posts\_listen\_live.py

