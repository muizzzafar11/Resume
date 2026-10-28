#!/usr/bin/env python3
"""Push tailored resumes to the muizzzafar11/Resume repo, one branch per job.

Run this from anywhere inside the repo on the Mac (it finds the repo root
itself). It expects the Mac repo layout: tailored/<slug>.tex next to
tailored/<slug>.pdf.

For each resume slug, in order:
  1. Check out a branch named <slug> (created from --base, default "main",
     if it does not exist yet locally).
  2. Compile tailored/<slug>.tex with pdflatex. If compilation fails, that
     slug is SKIPPED: nothing is committed or pushed for it.
  3. Commit tailored/<slug>.tex and tailored/<slug>.pdf, but only if they
     changed.
  4. Push the branch to origin (sets upstream on first push).

Which slugs:
  - Default: APPLIED_SLUGS below (jobs applied to so far, Oct 27, 2026).
    To add a newly applied job, append its slug to that list.
  - Pass slugs on the command line to process only those, e.g.:
        python3 push_tailored_resumes.py toronto-tempo-data-engineer
  - --all processes every .tex file found in tailored/ (this includes the
    base template and roles that were only tailored, not applied -- use it
    deliberately).

Safety:
  - Never force-pushes. If the remote branch has diverged history, the push
    fails for that slug and the script moves on.
  - Refuses to start with a dirty tracked working tree (untracked files are
    fine), so it never sweeps unrelated edits into a resume branch.
  - Cleans up pdflatex by-products (.aux/.log/.out) after each compile.

Requires: git and pdflatex on PATH. Exit code 0 only if every processed slug
was pushed; otherwise 1 (see the summary table at the end).
"""

import argparse
import os
import shutil
import subprocess
import sys

# Jobs applied to so far (submitted applications with a tailored resume).
# NOTE: the six Oct 27 evening tailors (Tempo, Job Bank Mississauga,
# Moneris, Movable Ink x2, Tangerine) are NOT in this list yet because they
# have not been applied to -- add their slugs here once they are submitted.
APPLIED_SLUGS = [
    "aequilibrium-senior-full-stack-developer",
    "penn-interactive-senior-data-engineer",
    "ntt-data-aws-data-engineer",
    "ntt-data-full-stack-developer",
    "valsoft-software-developer",
    "aviso-data-engineer",
    "intelerad-senior-software-developer",
    "ontinue-cloud-native-developer",
    "financeit-data-engineer",
    "opg-junior-software-engineer-full-stack",
    "td-data-engineer-ii",
    "sotera-health-database-administrator",
    "ciro-senior-database-administrator",
    "bmo-senior-database-administrator",
    "cpus-financial-data-analyst",
    "mnp-data-developer-term",
    "nesto-senior-data-engineer",
    "four-seasons-bi-engineer",
    "cloudvital-sql-database-administrator",
    "citi-intermediate-programmer-analyst",
    "synechron-cube-developer",
    "sunlife-infrastructure-dba",
    "amazon-data-engineer-early-career",
    "amazon-sr-business-intelligence-engineer",
]


def run(cmd, cwd, check=False):
    """Run cmd (list) in cwd; return the CompletedProcess (output captured)."""
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"command failed ({proc.returncode}): {' '.join(cmd)}\n"
            f"{proc.stdout}{proc.stderr}"
        )
    return proc


def repo_root(start):
    proc = run(["git", "rev-parse", "--show-toplevel"], cwd=start)
    if proc.returncode != 0:
        sys.exit("error: not inside a git repository (run from the Resume repo).")
    return proc.stdout.strip()


def branch_exists(root, branch):
    return run(
        ["git", "show-ref", "--verify", f"refs/heads/{branch}"], cwd=root
    ).returncode == 0


def compile_tex(tailored_dir, slug):
    """Compile tailored/<slug>.tex with pdflatex. Returns True on success."""
    tex = f"{slug}.tex"
    pdf = f"{slug}.pdf"
    pdf_path = os.path.join(tailored_dir, pdf)
    if os.path.exists(pdf_path):
        os.remove(pdf_path)  # prove the PDF came from this compile
    proc = run(
        ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", tex],
        cwd=tailored_dir,
    )
    # Clean by-products either way; they are regenerable.
    for ext in (".aux", ".log", ".out"):
        byproduct = os.path.join(tailored_dir, slug + ext)
        if os.path.exists(byproduct):
            os.remove(byproduct)
    if proc.returncode != 0 or not os.path.exists(pdf_path):
        print(f"  !! compile failed for {slug}:")
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-15:]
        print("\n".join("     " + line for line in tail))
        return False
    return True


def process_slug(root, tailored_dir, slug, base):
    tex_rel = os.path.join("tailored", f"{slug}.tex")
    pdf_rel = os.path.join("tailored", f"{slug}.pdf")
    if not os.path.exists(os.path.join(root, tex_rel)):
        return "skipped (no .tex file)"
    print(f"== {slug} ==")
    if branch_exists(root, slug):
        run(["git", "checkout", slug], cwd=root, check=True)
        print(f"  checked out existing branch {slug}")
    else:
        run(["git", "checkout", "-b", slug, base], cwd=root, check=True)
        print(f"  created branch {slug} from {base}")
    if not compile_tex(tailored_dir, slug):
        return "FAILED (compile)"
    run(["git", "add", tex_rel, pdf_rel], cwd=root, check=True)
    # Commit only if something actually changed.
    staged = run(["git", "diff", "--cached", "--quiet"], cwd=root)
    if staged.returncode != 0:
        run(
            ["git", "commit", "-m", f"Add tailored resume for {slug}"],
            cwd=root,
            check=True,
        )
        print("  committed .tex + .pdf")
    else:
        print("  no changes to commit")
    push = run(["git", "push", "-u", "origin", slug], cwd=root)
    if push.returncode != 0:
        print(f"  !! push failed for {slug}:\n{push.stdout}{push.stderr}")
        return "FAILED (push)"
    print(f"  pushed {slug}")
    return "pushed"


def main():
    parser = argparse.ArgumentParser(
        description="Compile and push tailored resumes, one branch per job."
    )
    parser.add_argument("slugs", nargs="*", help="resume slugs to process")
    parser.add_argument(
        "--all", action="store_true",
        help="process every .tex file in tailored/ instead of APPLIED_SLUGS",
    )
    parser.add_argument(
        "--base", default="main", help="branch to create new branches from"
    )
    args = parser.parse_args()

    if not shutil.which("git"):
        sys.exit("error: git not found on PATH.")
    if not shutil.which("pdflatex"):
        sys.exit("error: pdflatex not found on PATH (install MacTeX first).")

    root = repo_root(os.getcwd())
    tailored_dir = os.path.join(root, "tailored")
    if not os.path.isdir(tailored_dir):
        sys.exit(f"error: no tailored/ directory in repo root {root}")

    # Refuse a dirty tracked tree so unrelated edits never ride along.
    dirty = run(
        ["git", "status", "--porcelain", "--untracked-files=no"], cwd=root
    ).stdout.strip()
    if dirty:
        sys.exit(
            "error: tracked working tree is dirty; commit or stash first:\n"
            + dirty
        )

    if args.slugs:
        slugs = args.slugs
    elif args.all:
        slugs = sorted(
            f[:-4]
            for f in os.listdir(tailored_dir)
            if f.endswith(".tex") and not f.startswith(".")
        )
    else:
        slugs = list(APPLIED_SLUGS)
    if not slugs:
        sys.exit("nothing to do: no slugs selected and tailored/ is empty.")

    results = {}
    try:
        for slug in slugs:
            try:
                results[slug] = process_slug(root, tailored_dir, slug, args.base)
            except RuntimeError as exc:
                results[slug] = f"FAILED ({exc})"
            finally:
                # Always return to the base branch before the next slug.
                run(["git", "checkout", args.base], cwd=root)
    finally:
        run(["git", "checkout", args.base], cwd=root)

    print("\nSummary:")
    failed = False
    for slug, outcome in results.items():
        print(f"  {slug}: {outcome}")
        if outcome.startswith("FAILED"):
            failed = True
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
