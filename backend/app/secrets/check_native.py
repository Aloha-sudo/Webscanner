"""Build smoke for the full installed native runner, without network access."""
from pathlib import Path
import tempfile
from app.secrets.native import run_native

def main():
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary);source=root/'fixture';source.mkdir();output=root/'result';output.mkdir()
        (source/'id_rsa').write_text('-----BEGIN OPENSSH PRIVATE KEY-----\nFICTIONAL_BUILD_FIXTURE\n-----END OPENSSH PRIVATE KEY-----')
        result=run_native({'source':'local','targets':[str(source)],'local_paths':[str(source)]},'',output)
        assert result['status']=='completed' and result['finding_count']>0
        assert all(b'FICTIONAL_BUILD_FIXTURE' not in file.read_bytes() for file in output.iterdir() if file.is_file())
    print('PASS: native snaffler runner, local key discovery and redacted persistence')

if __name__=='__main__':main()
