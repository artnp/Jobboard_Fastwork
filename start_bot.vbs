Set WshShell = CreateObject("WScript.Shell")
' Run pythonw fastwork_bot.py completely hidden (0 = hidden window, False = don't wait for process to finish)
WshShell.Run "pythonw fastwork_bot.py", 0, False
