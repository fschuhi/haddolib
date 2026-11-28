Attribute VB_Name = "ScanSheets"
Option Explicit

Public Sub CreateScanSheet()

    Dim wsSource As Worksheet
    Dim wbTarget As Workbook
    Dim wsTarget As Worksheet
    Dim rSource As Range
    Dim rTarget As Range
    Dim rSourceRow As Range

    Dim sSheetName As String
    Dim sFileName As String
    Dim sBasePath As String
    Dim sFolder As String
    Dim sFullPath As String
    Dim sSeparator As String
    Dim vInvalidChar As Variant

    Dim oldScreenUpdating As Boolean
    Dim oldEnableEvents As Boolean
    Dim sErrorMessage As String

    oldEnableEvents = Application.EnableEvents
    SetSilentApplicationState
    
    On Error GoTo ErrorHandler

    If Not TypeOf Application.ActiveSheet Is Worksheet Then err.Raise vbObjectError + 1000, "CreateScanSheet", "Bitte zuerst ein Tabellenblatt aktivieren."

    ' Ausgangsblatt und Namen vor dem Erstellen der neuen Datei merken.
    Set wsSource = Application.ActiveSheet
    sSheetName = wsSource.name
    sBasePath = wsSource.Parent.Path

    If Len(sBasePath) = 0 Then err.Raise vbObjectError + 1001, "CreateScanSheet", "Bitte die Ausgangsdatei zuerst speichern."

    Application.ScreenUpdating = False
    Application.EnableEvents = False

    ' Zielordner: <Ordner der Ausgangsdatei>/data/import/
    sSeparator = Application.PathSeparator

    sFolder = sBasePath & sSeparator & "data"
    If Len(Dir$(sFolder, vbDirectory)) = 0 Then MkDir sFolder

    sFolder = sFolder & sSeparator & "import"
    If Len(Dir$(sFolder, vbDirectory)) = 0 Then MkDir sFolder

    ' In VBA steht "nn" für Minuten.
    sFileName = Format$(Now, "yyyymmdd_hhnnss") & "_" & sSheetName

    ' Für Dateinamen unzulässige Zeichen ersetzen.
    For Each vInvalidChar In Array("\", "/", ":", "*", "?", """", "<", ">", "|")
        sFileName = Replace$(sFileName, CStr(vInvalidChar), "_")
    Next vInvalidChar

    sFullPath = sFolder & sSeparator & sFileName & ".xlsx"

    ' Eine vorhandene Datei nicht versehentlich überschreiben.
    If Len(Dir$(sFullPath)) > 0 Then err.Raise vbObjectError + 1002, "CreateScanSheet", "Die Zieldatei existiert bereits:" & vbCrLf & sFullPath

    ' Neue Arbeitsmappe mit genau einem Tabellenblatt.
    Set wbTarget = Workbooks.Add(xlWBATWorksheet)
    Set wsTarget = wbTarget.Worksheets(1)
    wsTarget.name = sSheetName

    ' Werte an dieselben Zellpositionen übertragen, ohne Formeln.
    Set rSource = wsSource.UsedRange
    Set rTarget = wsTarget.Range(rSource.Address)

    'rTarget.Value2 = rSource.Value2

    ' Zellformate und Spaltenbreiten übernehmen.
    rSource.Copy
    rTarget.PasteSpecial Paste:=xlPasteFormats
    rTarget.PasteSpecial Paste:=xlPasteValues
    rTarget.PasteSpecial Paste:=xlPasteColumnWidths
    Application.CutCopyMode = False

    ' Zeilenhöhen ebenfalls übernehmen.
    For Each rSourceRow In rSource.Rows
        wsTarget.Rows(rSourceRow.Row).RowHeight = rSourceRow.RowHeight
    Next rSourceRow

    wbTarget.SaveAs Filename:=sFullPath, FileFormat:=xlOpenXMLWorkbook

    ' Exportdatei nach dem Speichern schließen.
    wbTarget.Close SaveChanges:=False
    Set wbTarget = Nothing
    GoTo CleanExit

ErrorHandler:
    sErrorMessage = "Export fehlgeschlagen:" & vbCrLf & err.Description

    On Error Resume Next
    If Not wbTarget Is Nothing Then wbTarget.Close SaveChanges:=False
    On Error GoTo 0


CleanExit:
    Application.CutCopyMode = False
    Application.EnableEvents = oldEnableEvents
    RevertApplicationState

    If Len(sErrorMessage) > 0 Then
        MsgBox sErrorMessage, vbExclamation, "CreateScanSheet"
    End If

    Exit Sub
End Sub

