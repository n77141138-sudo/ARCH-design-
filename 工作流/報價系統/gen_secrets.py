import json
from pathlib import Path

cred_file = Path(r'c:\Users\user\OneDrive\桌面\antigravity_ARCH\ARCH-design-\工作流\報價系統\arch-quote-system-5ab37e7fe80d.json')
if not cred_file.exists():
    print("ERROR: 找不到憑證檔案")
else:
    data = json.loads(cred_file.read_text(encoding='utf-8'))
    lines = ['[gcp_service_account]']
    for k, v in data.items():
        if isinstance(v, str):
            v_escaped = v.replace('\n', '\\n')
            lines.append(f'{k} = "{v_escaped}"')
        else:
            lines.append(f'{k} = "{v}"')
    output = '\n'.join(lines)
    print(output)
    
    # 同時寫出到 secrets_template.txt 方便複製
    out_path = Path(r'c:\Users\user\OneDrive\桌面\antigravity_ARCH\ARCH-design-\工作流\報價系統\secrets_template.txt')
    out_path.write_text(output, encoding='utf-8')
    print(f"\n✅ 已輸出至: {out_path}")
