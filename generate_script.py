import os, base64

build_path = r'c:\Users\ADMIN\Documents\Lurnexa\HRMS\static\img\mipmap-build'
out_py = r'c:\Users\ADMIN\Documents\Lurnexa\HRMS\static\apk\decode_icons.py'

lines = []
lines.append('import os, base64')
lines.append('res_dir = r"c:\\Users\\ADMIN\\Documents\\Lurnexa\\Lurnexa_Mobile_Desktop_Apps\\mobile-app\\android\\app\\src\\main\\res"')
lines.append('')
lines.append('files_data = {')

for root, dirs, files in os.walk(build_path):
    rel = os.path.relpath(root, build_path)
    for f in files:
        file_path = os.path.join(root, f)
        with open(file_path, 'rb') as fp:
            b64 = base64.b64encode(fp.read()).decode('ascii')
        key = os.path.join(rel, f).replace('\\', '/')
        lines.append(f'    "{key}": "{b64}",')

lines.append('}')
lines.append('')
lines.append('for rel_path, b64_str in files_data.items():')
lines.append('    dest_path = os.path.join(res_dir, rel_path.replace("/", os.sep))')
lines.append('    os.makedirs(os.path.dirname(dest_path), exist_ok=True)')
lines.append('    if os.path.exists(dest_path):')
lines.append('        try:')
lines.append('            os.remove(dest_path)')
lines.append('        except Exception:')
lines.append('            pass')
lines.append('    with open(dest_path, "wb") as fp:')
lines.append('        fp.write(base64.b64decode(b64_str))')
lines.append('    print(f"Decoded {rel_path}")')

with open(out_py, 'w', encoding='utf-8') as fp:
    fp.write('\n'.join(lines))

print(f'Generated script at {out_py}, size: {os.path.getsize(out_py)} bytes')
