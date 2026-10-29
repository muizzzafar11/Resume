#!/usr/bin/env python3
"""Publish each tailored/<name>.tex as resume.tex + resume.pdf on its own Git branch.

Run from anywhere: python automate_resumes.py
Requirements: Git, pdflatex (or change LATEX_COMMAND), configured origin push access.
"""
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'tailored'
LATEX_COMMAND = 'pdflatex'
REMOTE = 'origin'


def run(*args, cwd=ROOT, capture=False):
    result = subprocess.run(args, cwd=cwd, text=True, check=True,
                            stdout=subprocess.PIPE if capture else None,
                            stderr=subprocess.PIPE if capture else None)
    return result.stdout.strip() if capture else None


def branch_name(stem):
    name = re.sub(r'[^A-Za-z0-9._/-]+', '-', stem).strip('.-/')
    if not name or name.endswith('.lock') or '..' in name or '@{' in name:
        raise ValueError(f'Invalid branch name from {stem!r}')
    run('git', 'check-ref-format', '--branch', name, capture=True)
    return name


def main():
    if not SOURCE.is_dir():
        sys.exit(f'Missing folder: {SOURCE}')
    if not shutil.which(LATEX_COMMAND):
        sys.exit(f'{LATEX_COMMAND} not found in PATH; install a LaTeX distribution.')
    if run('git', 'rev-parse', '--show-toplevel', capture=True) != str(ROOT):
        sys.exit('Place this script in the Git repository root.')
    if run('git', 'status', '--porcelain', capture=True):
        sys.exit('Working tree is not clean. Commit/stash changes before running.')
    original = run('git', 'branch', '--show-current', capture=True)
    if not original:
        sys.exit('Start from a named branch, not detached HEAD.')
    run('git', 'remote', 'get-url', REMOTE, capture=True)

    pairs = []
    for tex in sorted(SOURCE.glob('*.tex')):
        pdf = tex.with_suffix('.pdf')
        if not pdf.exists():
            print(f'Skipping {tex.name}: matching PDF missing')
            continue
        pairs.append((tex.name, pdf.name, branch_name(tex.stem)))
    if not pairs:
        sys.exit('No .tex/.pdf pairs found in tailored/.')
    if len({p[2].lower() for p in pairs}) != len(pairs):
        sys.exit('Two filenames produce the same branch name.')

    # A temporary directory outside Git preserves source files across checkouts.
    # It also keeps any existing tailored/ folder untouched on the source branch.
    with tempfile.TemporaryDirectory(prefix='resume-publish-') as temp:
        staging = Path(temp)
        for tex_name, pdf_name, branch in pairs:
            shutil.copy2(SOURCE / tex_name, staging / tex_name)
            shutil.copy2(SOURCE / pdf_name, staging / pdf_name)
        try:
            for tex_name, pdf_name, branch in pairs:
                print(f'\n=== Publishing {branch} ===', flush=True)
                # Existing branches are updated; otherwise create from starting branch.
                exists = subprocess.run(['git', 'show-ref', '--verify', '--quiet', f'refs/heads/{branch}'], cwd=ROOT).returncode == 0
                if exists:
                    run('git', 'switch', branch)
                else:
                    run('git', 'switch', '-c', branch, original)
                # Branch-specific files are staged from outside the repo.
                shutil.copy2(staging / tex_name, ROOT / 'resume.tex')
                # Delete the old PDF before compilation; never publish stale output.
                (ROOT / 'resume.pdf').unlink(missing_ok=True)
                with tempfile.TemporaryDirectory(prefix='latex-build-') as build:
                    build_dir = Path(build)
                    # Compile from repo root for relative assets, output in temp dir.
                    run(LATEX_COMMAND, '-interaction=nonstopmode', '-halt-on-error',
                        f'-output-directory={build_dir}', 'resume.tex')
                    compiled = build_dir / 'resume.pdf'
                    if not compiled.is_file():
                        raise RuntimeError(f'Compilation produced no PDF for {branch}')
                    shutil.copy2(compiled, ROOT / 'resume.pdf')
                run('git', 'add', '--', 'resume.tex', 'resume.pdf')
                changes = subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=ROOT).returncode != 0
                if changes:
                    run('git', 'commit', '-m', f'Update resume: {branch}')
                else:
                    print('No changes to commit.')
                run('git', 'push', '-u', REMOTE, branch)
                print(f'Published {branch}', flush=True)
        finally:
            # Restore only when the worktree is clean; preserve failed build state for debugging.
            if not run('git', 'status', '--porcelain', capture=True):
                run('git', 'switch', original)
                print(f'\nRestored original branch: {original}')
            else:
                print('\nWorking tree has changes; leaving current branch for inspection.', file=sys.stderr)


if __name__ == '__main__':
    try:
        main()
    except (subprocess.CalledProcessError, OSError, ValueError, RuntimeError) as exc:
        sys.exit(f'ERROR: {exc}')
