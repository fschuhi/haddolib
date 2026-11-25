Attribute VB_Name = "Import"
Option Explicit

'*************************************
' import
'*************************************

' RunImport - orchestrate one import crossing.
'   rngBlock : the named input Range (header row + data rows), e.g. ImportBlock1.
'   Returns  : a Scripting.Dictionary of the Python summary, or Nothing if the
'              user cancelled or the block has no data rows.
Private Function RunImport(ByVal rngBlock As Range) As Dictionary
    Dim nDataRows As Long
    nDataRows = rngBlock.Rows.Count - 1            ' minus the header row

    If nDataRows < 1 Then
        MsgBox "The selected block has no data rows.", _
               vbExclamation, "haddolib import"
        Set RunImport = Nothing
        Exit Function
    End If

    If MsgBox("Import " & nDataRows & " row(s)?", _
              vbQuestion + vbOKCancel, "haddolib import") <> vbOK Then
        Set RunImport = Nothing
        Exit Function
    End If

    ' Hand the raw values across the boundary; Python does the rest and returns
    ' the delimited summary string through Application.Run.
    Dim summary As String
    summary = Application.Run("haddo_import", rngBlock.Value2)

    Set RunImport = SummaryToDictionary(summary)
End Function


Public Sub DbImport()
    Dim res As Object
    Set res = RunImport(Range(R_DbImport))
    If res Is Nothing Then Exit Sub                ' cancelled or empty block

    ' The return path is empirically unproven until the first live run: an empty
    ' dictionary means Application.Run gave nothing back. Say so plainly rather
    ' than showing a blank box.
    If res.Count = 0 Then
        MsgBox "Import ran but no summary was returned." & vbCrLf & _
               "Check the Python <-> VBA return path (Application.Run).", _
               vbExclamation, "haddolib import"
        Exit Sub
    End If

    Dim msg As String
    msg = res("summary_line")
    If Len(res("rejected_rows_file")) > 0 Then
        msg = msg & vbCrLf & vbCrLf & _
              "Rejected rows written to:" & vbCrLf & res("rejected_rows_file")
    End If

    MsgBox msg, vbInformation, "haddolib import"
End Sub



