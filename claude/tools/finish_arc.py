"""Direct controller for a separate, preserved post-campaign arc archive audit."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sys
from customkf.guard import ROOT, Limits, run
from customkf.prepare_stage2 import sha


def main():
    if os.environ.get("CUSTOMKF_RUN_DIR"): raise RuntimeError("Do not nest guards")
    campaign=Path(sys.argv[1]).resolve()
    manifest=json.loads((campaign/"validation.json").read_text())
    assert manifest["status"]=="arc_experiment_complete_not_accuracy_acceptance"
    folder=campaign/("review-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")); folder.mkdir()
    pins={f"claude/tools/{n}.py":sha(ROOT/f"claude/tools/{n}.py") for n in ("arc_review","finish_arc")}
    for name in pins:
        target=folder/"source"/name; target.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(ROOT/name,target)
    result,path=run(["claude.tools.arc_review",str(campaign)],Limits(timeout_s=120))
    shutil.copytree(path,folder/"review")
    report=dict(status="arc_followup_review_pass" if result["status"]=="ok" else "failed",
                campaign_manifest_sha256=sha(campaign/"validation.json"),source_sha256=pins,
                run={**result,"original_directory":str(path)})
    for name,digest in pins.items(): assert sha(ROOT/name)==digest,name
    report["artifacts_sha256"]={p.relative_to(folder).as_posix():sha(p) for p in folder.rglob("*") if p.is_file()}
    (folder/"manifest.json").write_text(json.dumps(report,indent=2)+"\n")
    print("Review archive: "+str(folder),flush=True)
    if result["status"]!="ok": raise RuntimeError("Audit failed; see preserved logs")
    print((folder/"review/review.json").read_text(),flush=True)


if __name__ == "__main__": main()
