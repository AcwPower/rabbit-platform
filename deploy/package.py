"""Build a source + production assets release. Never include secrets or node_modules."""
import argparse, tarfile
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('output');args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
assert (root/'frontend/dist/index.html').exists(), 'Run frontend build first'
skip={'node_modules','dist','__pycache__','.pytest_cache','.git','.venv'}
with tarfile.open(args.output,'w:gz') as tar:
    for directory in ('backend','frontend','deploy','docs'):
        for path in sorted((root/directory).rglob('*')):
            if not path.is_file() or any(x in skip for x in path.relative_to(root).parts): continue
            if path.name.startswith('.env') and path.name!='.env.example': continue
            if path.name in {'captain-preview.html','vite.captain-preview.config.js'}: continue
            tar.add(path,arcname=str(path.relative_to(root)))
    for name in ('README.md','.gitignore'):
        if (root/name).exists(): tar.add(root/name,arcname=name)
    for path in sorted((root/'frontend/dist').rglob('*')):
        if path.is_file(): tar.add(path,arcname='public/party/'+str(path.relative_to(root/'frontend/dist')))
print(args.output)
