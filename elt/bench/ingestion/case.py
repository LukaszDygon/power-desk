"""Entry point for case_body.py, safe to re-import: dlt's normalize workers are spawned processes that
import the main module, and must not re-run the experiment."""

if __name__ == "__main__":
    from pathlib import Path
    import runpy

    runpy.run_path(str(Path(__file__).with_name("case_body.py")), run_name="lab_case")
