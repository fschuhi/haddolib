Attribute VB_Name = "Factory"
Option Explicit

' clDataSheet allows easy access to cells and named columns
Public ProtocolDataSheet As clDataSheet
Public PhotosDataSheet As clDataSheet

'*************************************
' clDataSheet objects
'*************************************

Function CreateProtocolDataSheet() As clDataSheet
    Dim ds As New clDataSheet
    ds.Init Worksheets(WS_Protocol), H_Key
    Set CreateProtocolDataSheet = ds
End Function

Function CreatePhotosDataSheet() As clDataSheet
    Dim ds As New clDataSheet
    ds.Init Worksheets(WS_Photos), "import"
    Set CreatePhotosDataSheet = ds
End Function

Sub CreateDataSheets(bForce As Boolean)
    If bForce Then
        Set ProtocolDataSheet = Nothing
        Set PhotosDataSheet = Nothing
    End If
    If ProtocolDataSheet Is Nothing Then Set ProtocolDataSheet = CreateProtocolDataSheet()
    If PhotosDataSheet Is Nothing Then Set PhotosDataSheet = CreatePhotosDataSheet()
End Sub


Sub ForceCreateDataSheets()
    ' needed for hard reload
    ' called from JumpStation
    CreateDataSheets True
End Sub


'*************************************
' clHaddoBookshelf objects (transient)
'*************************************

Function CreateHaddoBookshelf(wsShelf As Worksheet, sHaddoHandle As String)
    ShapeClick.UnregisterHaddoBookshelf wsShelf
    Dim hbs As New clHaddoBookshelf
    hbs.Init wsShelf, sHaddoHandle
    ShapeClick.RegisterHaddoBookshelf hbs, wsShelf
    Set CreateHaddoBookshelf = hbs
End Function

