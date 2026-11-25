Attribute VB_Name = "BookInfo"
Option Explicit

Sub ShowBookInfo(sQuery As String)
    Const PROJECT = "~/Projects/haddolib"

    Dim oShell As Object:  Set oShell = CreateObject("WScript.Shell")
    Dim tmpFile As String: tmpFile = Environ$("TEMP") & "\isbndb_out.csv"

    Dim sCmd As String
    sCmd = "cmd /c ssh mac ""cd " & PROJECT & _
           " && .venv/bin/python scripts/isbndb_query.py --synopsis '" & _
           sQuery & "'"" > """ & tmpFile & """ 2>nul"
    
    oShell.Run sCmd, 0, True   ' 0 = hidden, True = wait for completion

    ' ---- read the file ----
    Dim sOut As String
    Dim ff As Integer: ff = FreeFile
    If Dir(tmpFile) = "" Then
        MsgBox "No results found for " & sQuery, vbInformation, "Book Info"
        Exit Sub
    End If
    
    ' ---- read the file ----
    ' 03.07.26 Input$ reads bytes and interprets them using the system ANSI code page (Windows-1252)
    'Open tmpFile For Input As #ff
    '    sOut = Input$(LOF(ff), ff)
    'Close #ff
    'Kill tmpFile
    
    ' using ADODB.Stream (a) uses UTF-8 (d.h. deutsche Umlaute sind ok) and (b) silently removes the BOM marker
    Dim stm As Object: Set stm = CreateObject("ADODB.Stream")
    stm.Type = 2                 ' adTypeText
    stm.Charset = "utf-8"        ' decode bytes as UTF-8; consumes the BOM
    stm.Open
    stm.LoadFromFile tmpFile
    sOut = stm.ReadText(-1)      ' -1 = adReadAll
    stm.Close
    Kill tmpFile

    If Len(Trim$(sOut)) = 0 Then
        MsgBox "No results found for " & sQuery & ", VPN on?", vbInformation, "Book Info"
        Exit Sub
    End If

    ' ---- grab first data line (skip the CSV header) ----
    Dim dataLine As String
    dataLine = FirstDataLine(sOut)
    If Len(dataLine) = 0 Then
        MsgBox "Could not parse script output.", vbExclamation, "Book Info"
        Exit Sub
    End If

    ' ---- parse semicolon-delimited CSV ----
    Dim fld() As String
    fld = SplitCSVLine(dataLine, ";")

    If UBound(fld) < 9 Then
        MsgBox "Unexpected field count (" & UBound(fld) + 1 & ").", _
               vbExclamation, "Book Info"
        Exit Sub
    End If

    Dim sTitle  As String:  sTitle = Dequote(fld(2))
    Dim sAuthor As String:  sAuthor = Dequote(fld(3))
    Dim sSynop  As String:  sSynop = Dequote(fld(9))

    MsgBox sTitle & vbCrLf & sAuthor & vbCrLf & vbCrLf & sSynop, vbOKOnly, "Book Info"
End Sub


Private Function FirstDataLine(ByVal s As String) As String
    Dim ln() As String, i As Long, hdrDone As Boolean
    ln = Split(Replace$(s, vbCrLf, vbLf), vbLf)
    For i = 0 To UBound(ln)
        If Len(Trim$(ln(i))) = 0 Then GoTo Nxt
        If Not hdrDone Then hdrDone = True: GoTo Nxt
        FirstDataLine = Trim$(ln(i))
        Exit Function
Nxt:
    Next i
    FirstDataLine = ""
End Function


Private Function SplitCSVLine(ByVal sLine As String, ByVal delim As String) As String()
    Dim r() As String, n As Long
    ReDim r(0 To 31)
    Dim inQ As Boolean, fStart As Long, i As Long, c As String

    fStart = 1: inQ = False: n = 0
    For i = 1 To Len(sLine)
        c = Mid$(sLine, i, 1)
        If c = """" Then
            inQ = Not inQ
        ElseIf c = delim And Not inQ Then
            r(n) = Mid$(sLine, fStart, i - fStart)
            n = n + 1
            If n > UBound(r) Then ReDim Preserve r(0 To n + 31)
            fStart = i + 1
        End If
    Next i
    r(n) = Mid$(sLine, fStart)
    ReDim Preserve r(0 To n)
    SplitCSVLine = r
End Function


Private Function Dequote(ByVal s As String) As String
    s = Trim$(s)
    If Len(s) >= 2 Then
        If Left$(s, 1) = """" And Right$(s, 1) = """" Then
            s = Mid$(s, 2, Len(s) - 2)
        End If
    End If
    Dequote = Replace$(s, """""", """")
End Function

