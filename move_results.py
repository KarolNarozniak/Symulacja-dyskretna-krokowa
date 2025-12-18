import os, shutil
from datetime import datetime

now = datetime.now().strftime('%Y%m%d_%H%M%S')
root = '.'
for fname in os.listdir(root):
    if not os.path.isfile(fname):
        continue
    if fname.lower().endswith(('.png', '.csv')):
        base, ext = os.path.splitext(fname)
        new = os.path.join('results', f"{base}_{now}{ext}")
        shutil.move(fname, new)
        print('moved', fname, '->', new)
print('done')
