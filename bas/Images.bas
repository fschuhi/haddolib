Attribute VB_Name = "Images"
Option Explicit


'*************************************
' image files are in 2 locations
'*************************************

Sub TestDetermineQualifiedImagePath()
    MsgBox DetermineQualifiedImagePath("https://images.isbndb.com/covers/1146123482742.jpg")
    MsgBox DetermineQualifiedImagePath("rack_01 2026-02-16 21.31.34.jpg")
End Sub

Public Function DetermineQualifiedImagePath(s As String)
    Dim sPath As String
    Dim sfn As String
    If StartsWith(s, "http") Then
        sfn = RegMatch(s, "[0-9]+.jpg$", 0)
        DetermineQualifiedImagePath = COVERS_PATH & sfn
    Else
        sfn = s
        DetermineQualifiedImagePath = PICTURE_PATH & s
    End If
End Function


'*************************************
' open (on keypress)
'*************************************

Public Sub OpenFileWithoutPath(sfn As String)
    Dim sPath As String
    If StartsWith(sfn, "http") Then
        sfn = RegMatch(sfn, "[0-9]+.jpg$", 0)
        sPath = COVERS_PATH
    Else
        sPath = PICTURE_PATH
    End If
    OpenFile sfn, sPath
End Sub


Public Sub OpenFile(sfn As String, sPath As String)
    sPath = EnsureTrailingBackslash(sPath)
    Dim sFullPath As String: sFullPath = sPath & sfn
    Dim oShell As Object: Set oShell = CreateObject("WScript.Shell")
    oShell.Run """" & sFullPath & """", 1, False
    Set oShell = Nothing
End Sub


'*************************************
' Images on sheet
'*************************************

Sub TestPositionImage()
    Dim ws As Worksheet: Set ws = Worksheets("Box")
    Dim rAnchor As Range: Set rAnchor = ws.Range("Anchor")
    Dim sCoverURL As String: sCoverURL = "https://images.isbndb.com/covers/1146123482742.jpg"
    Dim sfn As String: sfn = DetermineQualifiedImagePath(sCoverURL)
    Debug.Assert FileExists(sfn)
    PositionImage sfn, rAnchor, 13, 3
End Sub


Sub RemoveAllImagesOnActiveSheet()
    RemoveAllImages ActiveSheet
End Sub

Sub RemoveAllImages(ws As Worksheet)
    ' Loop backwards because we're deleting
    Dim i As Long
    For i = ws.Shapes.Count To 1 Step -1
        Dim shp As Shape: Set shp = ws.Shapes(i)
        If shp.Type = msoPicture Then
            shp.Delete
        End If
    Next i
End Sub


Function PositionImage(sfnImage As String, rTopLeft As Range, nRows As Integer, nCols As Integer) As Shape
    ' Resolve to a single cell
    Dim rCell As Range: Set rCell = rTopLeft.Cells(1)
    Dim ws As Worksheet: Set ws = rCell.Worksheet

    Dim i As Long

    ' Calculate target height by summing row heights
    Dim dblHeight As Double: dblHeight = 0
    For i = 0 To nRows - 1
        dblHeight = dblHeight + ws.Rows(rCell.Row + i).Height
    Next i

    ' Calculate target width by summing column widths
    Dim dblWidth As Double: dblWidth = 0
    For i = 0 To nCols - 1
        dblWidth = dblWidth + ws.Columns(rCell.Column + i).Width
    Next i

    ' Insert the image at the cell's position
    Dim shp As Shape: Set shp = ws.Shapes.AddPicture( _
        Filename:=sfnImage, _
        LinkToFile:=msoFalse, _
        SaveWithDocument:=msoTrue, _
        Left:=rCell.Left, _
        Top:=rCell.Top, _
        Width:=0, _
        Height:=0)

    ' Restore native dimensions so the aspect ratio is correct
    shp.LockAspectRatio = msoFalse
    shp.ScaleWidth 1, msoTrue
    shp.ScaleHeight 1, msoTrue

    ' Lock aspect ratio and fit to height first
    shp.LockAspectRatio = msoTrue
    shp.Height = dblHeight

    ' If the image is still too wide, fit to width instead
    If shp.Width > dblWidth Then
        shp.Width = dblWidth
    End If

    ' Pin the top-left corner to the cell
    shp.Left = rCell.Left
    shp.Top = rCell.Top

    Set PositionImage = shp
End Function
