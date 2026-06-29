import os

templates_dir = 'templates'

for root, dirs, files in os.walk(templates_dir):
    for file in files:
        if file.endswith('.html'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            modified = False
            
            # Replace 'Lurnexa HRMS' with 'Lurnexa'
            if 'Lurnexa HRMS' in content:
                content = content.replace('Lurnexa HRMS', 'Lurnexa')
                modified = True
                
            # Replace sidebar 'HRMS' label in templates/base.html
            if file == 'base.html' and 'me-2"></i> HRMS' in content:
                content = content.replace('me-2"></i> HRMS', 'me-2"></i> Lurnexa')
                modified = True
                
            if modified:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"Updated branding in {filepath}")
