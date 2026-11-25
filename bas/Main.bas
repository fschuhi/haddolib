Attribute VB_Name = "Main"
Option Explicit


'*************************************
' helpers
'*************************************

' SummaryToDictionary - turn the delimited summary string into a Scripting.Dictionary.
'   Wire format (BRIDGE_CONTRACT.md section 4): "key" & vbTab & "value" lines
'   joined by vbLf. Split on vbLf, then each non-empty line once on vbTab.
Function SummaryToDictionary(ByVal s As String) As Dictionary
    Dim d As Object
    Set d = CreateObject("Scripting.Dictionary")

    Dim lines() As String, kv() As String, i As Long
    lines = Split(s, vbLf)
    For i = LBound(lines) To UBound(lines)
        If Len(lines(i)) > 0 Then
            kv = Split(lines(i), vbTab)
            If UBound(kv) >= 1 Then
                d(kv(0)) = kv(1)
            End If
        End If
    Next i

    Set SummaryToDictionary = d
End Function



