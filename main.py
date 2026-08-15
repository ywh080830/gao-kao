# -*- coding: utf-8 -*-
"""引导入口（明文，勿加密）。

先安装解密加载器，把仓库中的 *.py.enc 还原到内存/临时目录并加入 sys.path，
随后以普通方式启动应用入口 `app._main`。
"""
import loader

loader.install()

if __name__ == "__main__":
    import app._main
    app._main.main()
