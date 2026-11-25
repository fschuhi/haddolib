Attribute VB_Name = "Buttons"
Option Explicit

' ((ENXCKEQ)) refactor acessing R_Tags and R_MustAllMatch
' ((UOLQKYL)) do not display more than 200 books on a shelf


'*************************************
' standard buttons
'*************************************

Sub Button_GenerateWorksheetsMatrix()
    GenerateWorksheetsMatrix
    UpdateDataFlowBoxes
End Sub

Sub Button_GenerateDot()
    GenerateDot
End Sub

Sub Button_HideDisplayHeadingsAndFreezeAllPanes()
    HideDisplayHeadings
    FreezeAllPanes
End Sub

Sub Button_PositionSelections()
    PositionSelectionOnEverySheet
    Worksheets("Intro").Activate
End Sub

Sub Button_SetVersion()
    SetVersion
End Sub

Sub Button_UpdateDataFlowBoxes()
    UpdateDataFlowBoxes
End Sub


'*************************************
' rack/box book sheets
'*************************************

Sub Button_DisplayBooksInBox()
    ClearStatusBar
    Dim iRack As Integer: iRack = ActiveSheet.Range(H_Rack)
    Dim iBox As Integer: iBox = ActiveSheet.Range(H_Box)
    DisplayBooksInBox iRack, iBox
End Sub

Sub Button_GotoNextBox()
    Dim iNextRack As Integer
    Dim iNextBox As Integer
    DetermineNextBox ActiveSheet.Range(H_Rack), ActiveSheet.Range(H_Box), iNextRack, iNextBox
    DisplayBooksInBox iNextRack, iNextBox
End Sub

Sub Button_GotoPrevBox()
    Dim iPrevRack As Integer
    Dim iPrevBox As Integer
    DeterminePrevBox ActiveSheet.Range(H_Rack), ActiveSheet.Range(H_Box), iPrevRack, iPrevBox
    DisplayBooksInBox iPrevRack, iPrevBox
End Sub


'*************************************
' tags sheets
'*************************************

Sub Button_DisplayBooksWithMatchingTags()
    CreateDataSheets False
    
    ' ((ENXCKEQ)) refactor acessing R_Tags and R_MustAllMatch
    Dim sTags As String: sTags = ActiveSheet.Range(R_Tags)
    Dim bMustMatchAll As Boolean: bMustMatchAll = ActiveSheet.Range(R_MustAllMatch)
    
    DisplayBooksForTags sTags, bMustMatchAll
    ' ((UOLQKYL)) do not display more than 200 books on a shelf
End Sub


'*************************************
' authors sheets
'*************************************

Sub Button_DisplayBooksOfAuthors()
    Dim sAuthors As String: sAuthors = ActiveSheet.Range(R_Authors)
    DisplayBooksForAuthors sAuthors
End Sub


'*************************************
' title sheets
'*************************************

Sub Button_DisplayBooksWithTitle()
    Dim sTitle As String: sTitle = ActiveSheet.Range(R_Title)
    DisplayBooksForTitle sTitle
End Sub


'*************************************
' haddolib
'*************************************

Sub Button_Touch()
    Touch Range(R_Touchpoint)
End Sub

Sub Button_HaddoSweepHandles()
    VBA_haddo_sweep_handles
End Sub

Sub Button_Import()
   DbImport
End Sub
