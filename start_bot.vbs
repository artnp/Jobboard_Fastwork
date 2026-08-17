Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strPath = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = strPath
' รัน bot ด้วย python.exe (bot จะ FreeConsole ตัวเองเพื่อซ่อน console window)
WshShell.Run "python """ & strPath & "\fastwork_bot.py""", 0, False
