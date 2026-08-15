# loader.py — 明文引导加载器（本文件与引导 main.py 必须保持明文，切勿加密）
#
# 作用：在运行时把仓库中的 *.py.enc 密文解密到临时目录并加入 sys.path，
# 使 `import app` 等依旧可以正常工作。解密使用纯标准库实现（SHA-256 派生
# 密钥流 + XOR），不依赖任何第三方包，因此在普通 Python 环境与 PyInstaller
# 打包后的 EXE 中均可运行。
import os
import sys
import hashlib
import tempfile

# 32 字节密钥（与加密脚本 make_enc.py 共用同一把）。
KEY = bytes.fromhex("c0d4042aa67e6377a76408139bab994f6e0cc2da4f42688de10cdf03a5c08a43")


def _keystream(key, nonce, length):
    out = bytearray()
    i = 0
    while len(out) < length:
        out += hashlib.sha256(nonce + i.to_bytes(4, "big") + key).digest()
        i += 1
    return bytes(out[:length])


def _decrypt(blob):
    if len(blob) < 8:
        return blob
    nonce = blob[:8]
    ct = blob[8:]
    return bytes(a ^ b for a, b in zip(ct, _keystream(KEY, nonce, len(ct))))


def decrypt_file(path):
    with open(path, "rb") as f:
        return _decrypt(f.read())


_TMP = None


def _enc_root():
    # 打包后的 EXE：密文随 datas 解压到 _MEIPASS；普通仓库：本文件所在目录。
    if getattr(sys, "_MEIPASS", None):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def decrypt_tree(src_root, dst_root):
    n = 0
    for dirpath, _dirs, files in os.walk(src_root):
        for fn in files:
            if fn.endswith(".py.enc"):
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, src_root)[:-4]  # 去掉 .enc 后缀
                dst = os.path.join(dst_root, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with open(dst, "wb") as f:
                    f.write(decrypt_file(full))
                n += 1
    return n


def install():
    """解密全部 *.py.enc 到临时目录并插入 sys.path，返回临时目录。幂等。"""
    global _TMP
    if _TMP is not None:
        return _TMP
    root = _enc_root()
    _TMP = tempfile.mkdtemp(prefix="gk_obf_")
    decrypt_tree(root, _TMP)
    sys.path.insert(0, _TMP)
    return _TMP


if __name__ == "__main__":
    print("decrypted into:", install())
