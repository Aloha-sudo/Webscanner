"""Validate a completed browser capture before updating README or publishing images."""
from pathlib import Path
import hashlib
import html
import json
import re
import zipfile

SCENES = [
 '01-overview-dark','02-scan-results-dark','03-host-card-dark','04-dns-settings-dark',
 '05-screenshot-gallery-dark','06-screenshot-viewer-dark','07-comparison-dark','08-network-map-dark',
 '09-neighborhood-dark','10-service-visibility-dark','11-observation-path-dark','12-evidence-table-dark',
 '13-project-description-dark','14-project-import-dark',
]
START='<!-- WEBSCANNER_GALLERY_START -->'
END='<!-- WEBSCANNER_GALLERY_END -->'


def validate(root):
    folder=root/'docs/images/gallery'
    manifest=json.loads((folder/'manifest.json').read_text())
    if manifest.get('theme')!='dark' or manifest.get('backend_writes')!=0:
        raise ValueError('The gallery must be dark and have zero backend writes')
    if manifest.get('unexpected_requests') or manifest.get('browser_errors'):
        raise ValueError('Capture contains unexpected requests or browser errors')
    shots=manifest.get('shots',[])
    if {shot['file'] for shot in shots}!={name+'.png' for name in SCENES} or len(shots)!=14:
        raise ValueError('All fourteen real browser scenes are required')
    for shot in shots:
        content=(folder/shot['file']).read_bytes()
        if not content.startswith(b'\x89PNG\r\n\x1a\n') or len(content)<1000:
            raise ValueError('Invalid or empty screenshot: '+shot['file'])
        if hashlib.sha256(content).hexdigest()!=shot['sha256']:
            raise ValueError('Screenshot checksum mismatch: '+shot['file'])
    if not (folder/'contact-sheet-dark.png').is_file():
        raise ValueError('The dark contact sheet is missing')
    return manifest


def gallery_table(manifest,language):
    shots={shot['file']:shot for shot in manifest['shots']}
    names=['02-scan-results-dark','03-host-card-dark','05-screenshot-gallery-dark','07-comparison-dark',
           '09-neighborhood-dark','10-service-visibility-dark','11-observation-path-dark','12-evidence-table-dark']
    parts=['<table>']
    for index in range(0,len(names),2):
        parts.append('<tr>')
        for name in names[index:index+2]:
            shot=shots[name+'.png'];title=html.escape(shot[language]);image='docs/images/gallery/'+shot['file']
            parts.append(f'<td width="50%"><a href="{image}"><img src="{image}" alt="{title}" width="100%"></a><br><strong>{title}</strong></td>')
        parts.append('</tr>')
    parts.append('</table>')
    return '\n'.join(parts)


def updated_readme(source,manifest,language):
    en=language=='en'
    title='WebScanner dark interface gallery' if en else 'WebScanner: галерея тёмного интерфейса'
    image='docs/images/gallery/08-network-map-dark.png'
    hero=f'[![{title}]({image})]({image})'
    source=re.sub(r'^\[!\[.*?\]\(.*?\)\]\(.*?\)$',hero,source,count=1,flags=re.M)
    caption=('*Actual WebScanner interface in dark mode. Browser captures use synthetic API fixtures; no real organization data is shown.*'
             if en else '*Настоящий интерфейс WebScanner в тёмной теме. Кадры сняты браузером на демонстрационных ответах API; реальных данных организаций здесь нет.*')
    source=re.sub(r'^\*(?:Actual WebScanner|Настоящий SVG|Настоящий интерфейс).*?\*$',caption,source,count=1,flags=re.M)
    heading='## Interface gallery' if en else '## Интерфейс программы'
    intro=('All scenes use the same dark theme. Click any image for the full-size capture. '
           '[All 14 screens, including DNS, screenshot viewer and project import →](docs/gallery.md)'
           if en else 'Все кадры сняты в одной тёмной теме. Нажмите на изображение, чтобы открыть его целиком. '
           '[Все 14 экранов: DNS, просмотр скриншотов, описание и импорт проекта →](docs/gallery.md)')
    block='\n'.join([START,heading,'',intro,'',gallery_table(manifest,language),END])
    if START in source:
        return re.sub(re.escape(START)+r'.*?'+re.escape(END),lambda _:block,source,flags=re.S)
    anchor='## Why the graph matters' if en else '## Зачем нужна такая карта'
    if anchor not in source:
        raise ValueError('README structure changed; refusing to insert images into an unknown location')
    return source.replace(anchor,block+'\n\n'+anchor,1)


def publish(root):
    root=Path(root).resolve()
    manifest=validate(root)
    en=updated_readme((root/'README.md').read_text(),manifest,'en')
    ru=updated_readme((root/'README.ru.md').read_text(),manifest,'ru')
    lines=['# WebScanner — dark interface gallery','',
           'Real WebScanner UI captured in Chromium with intercepted synthetic API fixtures. All fourteen scenes use dark mode, an English interface and UTC with a 24-hour clock. No production projects were read or modified.','',
           '**[Contact sheet](images/gallery/contact-sheet-dark.png)** · [Capture manifest](images/gallery/manifest.json) · [Capture procedure](gallery-capture.md)','']
    for shot in manifest['shots']:
        lines.extend([f"## {shot['en']} / {shot['ru']}",'',f"![{shot['en']}](images/gallery/{shot['file']})",''])
    # Validation is complete before any README or public gallery is replaced.
    (root/'README.md').write_text(en)
    (root/'README.ru.md').write_text(ru)
    (root/'docs/gallery.md').write_text('\n'.join(lines))
    paths=['.gitignore','README.md','README.ru.md','docs/gallery.md','docs/gallery-capture.md','docs/guide.ru.md',
           'docs/images/network-map-demo.svg','docs/images/network-map-demo.png',
           'examples/README.md','examples/demo-project.zip','examples/demo-visibility.json',
           'scripts/capture_gallery.sh','scripts/gallery/capture.cjs','scripts/gallery/fixtures.json','scripts/gallery/publish.py']
    paths.extend('docs/images/gallery/'+shot['file'] for shot in manifest['shots'])
    paths.extend(['docs/images/gallery/contact-sheet-dark.png','docs/images/gallery/manifest.json'])
    if len(paths)>100:raise ValueError('Gallery update exceeds the browser upload file limit')
    archive=root.parent/'gallery-for-github.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as output:
        for relative in paths:
            if not (root/relative).is_file():raise ValueError('Missing gallery file: '+relative)
            output.write(root/relative,relative)
    with zipfile.ZipFile(archive) as check:
        if check.testzip():raise ValueError('Gallery archive verification failed')
    print(f'Gallery ready: {archive} ({len(paths)} files). Extract and upload the contents in one browser upload.')
    return archive


if __name__=='__main__':
    try:
        publish(Path(__file__).resolve().parents[2])
    except (OSError,ValueError,KeyError) as exc:
        raise SystemExit('Gallery not published: '+str(exc))
