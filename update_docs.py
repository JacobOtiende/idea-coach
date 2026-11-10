"""Update CHANGELOG.md and ROADMAP.md now. The app also does this on its own.

Usage:  python update_docs.py
"""
import db as dbmod
import devlog
import settings


def main() -> None:
    provider = None
    if settings.ANTHROPIC_API_KEY:
        from llm import AnthropicProvider
        provider = AnthropicProvider()
    report = devlog.sync_docs(dbmod.DB(), provider)
    print(f"Docs updated: {report['entries']} change entries, {report['milestones']} milestones.")


if __name__ == "__main__":
    main()
