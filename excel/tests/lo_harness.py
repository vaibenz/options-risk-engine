"""Load .bas modules into a LibreOffice Calc doc in VBA compat mode and call
their functions and subs, so the VBA can be tested without Excel."""
import os
import subprocess
import time

import uno
from com.sun.star.beans import PropertyValue


def prop(name, value):
    p = PropertyValue()
    p.Name, p.Value = name, value
    return p


class LO:
    def __init__(self, port=2099):
        self.proc = subprocess.Popen([
            "soffice", "--headless", "--invisible", "--norestore", "--nologo",
            f"--accept=socket,host=localhost,port={port};urp;",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        local = uno.getComponentContext()
        resolver = local.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", local)
        for _ in range(60):
            try:
                self.ctx = resolver.resolve(f"uno:socket,host=localhost,port={port};urp;StarOffice.ComponentContext")
                break
            except Exception:
                time.sleep(0.5)
        smgr = self.ctx.ServiceManager
        self.desktop = smgr.createInstanceWithContext("com.sun.star.frame.Desktop", self.ctx)

    def open(self, path=None):
        url = "private:factory/scalc" if path is None else uno.systemPathToFileUrl(os.path.abspath(path))
        self.doc = self.desktop.loadComponentFromURL(url, "_blank", 0, (prop("Hidden", True), prop("MacroExecutionMode", 4)))
        return self.doc

    def add_module(self, name, bas_path):
        src = open(bas_path).read().replace("\r\n", "\n")
        lines = [ln for ln in src.split("\n") if not ln.startswith("Attribute VB_")]
        code = "Option VBASupport 1\n" + "\n".join(lines)
        libs = self.doc.BasicLibraries
        if not libs.hasByName("Standard"):
            libs.createLibrary("Standard")
        lib = libs.getByName("Standard")
        if lib.hasByName(name):
            lib.replaceByName(name, code)
        else:
            lib.insertByName(name, code)
        self.doc.BasicLibraries.VBACompatibilityMode = True

    def call(self, module, func, *args):
        sp = self.doc.getScriptProvider()
        script = sp.getScript(f"vnd.sun.star.script:Standard.{module}.{func}?language=Basic&location=document")
        res = script.invoke(tuple(args), (), ())
        return res[0]

    def close(self):
        try:
            self.doc.close(True)
        except Exception:
            pass
        try:
            self.desktop.terminate()
        except Exception:
            pass
        self.proc.wait(timeout=20)
