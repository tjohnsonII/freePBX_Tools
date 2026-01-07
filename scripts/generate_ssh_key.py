import os
import sys
from paramiko import RSAKey

BASE = os.path.join('E:\\DevTools', '.ssh')
PRIVATE_PATH = os.path.join(BASE, 'id_rsa')
PUBLIC_PATH = PRIVATE_PATH + '.pub'

os.makedirs(BASE, exist_ok=True)
key = RSAKey.generate(4096)
with open(PRIVATE_PATH, 'w') as f:
    key.write_private_key(f)
pub = f"{key.get_name()} {key.get_base64()}"
with open(PUBLIC_PATH, 'w') as f:
    f.write(pub)
print('Generated SSH key pair:')
print('Private:', PRIVATE_PATH)
print('Public:', PUBLIC_PATH)
print('Public key contents:\n', pub)
