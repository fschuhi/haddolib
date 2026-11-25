VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
END
Attribute VB_Name = "clHaddoBookshelf"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Option Explicit

' table view
Const N_CoverHeightInRows = 12
Const N_CoverWidthInCols = 2
Const N_HorizontalOffsetToNextCover = N_CoverWidthInCols + 1
Const N_VerticalOffsetToNextRowOfCovers = N_CoverHeightInRows + 3
Const N_CoversPerRow = 9

Const COL_book_id = "book_id"
Const COL_isbn13 = "isbn13"
Const COL_space_label = "space_label"
Const COL_bin_label = "bin_label"
Const COL_position = "position"
Const COL_cover_ref = "cover_ref"
Const COL_tags = "tags"

Dim m_wsBookshelf As Worksheet
Dim m_rRowAnchor As Range

' Dim m_rISBN13sOnProtocol As Range
' Dim m_rPhotosOnProtocol As Range
' Dim m_rTagsOnProtocol As Range


Dim m_sHaddoHandle As String
Dim m_iLen As Integer

'*************************************
' init & terminate
'*************************************

Sub Init(ws As Worksheet, sHaddoHandle As String)
    Set m_wsBookshelf = ws
    Set m_rRowAnchor = m_wsBookshelf.Range(R_Anchor)
    m_sHaddoHandle = sHaddoHandle
    m_iLen = GetHaddoBooksLen(sHaddoHandle)
    ShowStatus FS("# has # rows", sHaddoHandle, m_iLen)
End Sub

Private Sub Class_Terminate()
    Dim sReleased As String: sReleased = IIf(ReleaseHaddoHandle(m_sHaddoHandle), "released", "**NOT** released")
    ShowStatus FS("TERMINATED bookshelf on #, #: #", m_wsBookshelf.name, m_sHaddoHandle, sReleased)
End Sub


'*************************************
' searching for a field value
'*************************************

Function MatchField(vPassedValue, sField As String) As Integer
    Dim iRow As Integer
    For iRow = 1 To m_iLen
        Dim vValue: vValue = GetHaddoBooksFieldInRow(m_sHaddoHandle, sField, iRow)
        If vValue = vPassedValue Then
            MatchField = iRow
            Exit Function
        End If
    Next
    MatchField = 0
End Function


'*************************************
' doubleclick on image
'*************************************

Sub HandleShapeClicked(rTarget As Range)
    ' passed rTarget is the cell which matches the upper left corner of the image
    
    Dim rTags As Range: Set rTags = rTarget.Offset(N_CoverHeightInRows + 1, 0)
    
    ' "visual book ID" = either ISBN13 or "rack_.." photo
    Dim sVisualBookID As String: sVisualBookID = rTarget.Offset(N_CoverHeightInRows, 0)
    Dim iRow As Integer
    If EndsWith(sVisualBookID, ".jpg") Then
        ' it's a photo
        iRow = MatchField(sVisualBookID, COL_cover_ref)
    Else
        ' it's an ISBN13
        iRow = MatchField(sVisualBookID, COL_isbn13)
    End If
    
    Debug.Assert iRow > 0
    
    ' we use global variable to communicate to and from the tags form
    Dim frm As New UserFormTags
    With frm
        .Tags = GetHaddoBooksFieldInRow(m_sHaddoHandle, COL_tags, iRow)
        .Caption = "Book ID: " & sVisualBookID
        .Show
        
        Dim iBookID As Integer: iBookID = GetHaddoBooksFieldInRow(m_sHaddoHandle, COL_book_id, iRow)
        ' writes to database, but m_sHaddoHandle snapshot unchanged!
        SetHaddoTags iBookID, .Tags
        Application.Run "haddo_refresh_handle", m_sHaddoHandle
        
        ' in the past we didn't have the problem, because stored database (on "Protocol") and row
        ' set (also pointing to "Protocol") were the same
        'm_rTagsOnProtocol.Cells(ix) = .Tags
        rTags = .Tags
    End With
    Unload frm
End Sub


'*************************************
' doubleclick on image
'*************************************

Public Sub DisplayBooks()
    CreateDataSheets False
    SetSilentApplicationState
    On Error GoTo done
    
    Dim rAnchor As Range: Set rAnchor = m_rRowAnchor
    
    ' remove dynamic content
    RemoveAllImages m_wsBookshelf
    m_wsBookshelf.Range(rAnchor.Row & ":" & rAnchor.Row + 1000).Clear
    
    Dim ixCoverInRow As Integer: ixCoverInRow = 1
    
    ' StartTimer
    
    Dim iRow As Integer
    For iRow = 1 To m_iLen
        ' get the file from the cover
        Dim sCoverRef As String: sCoverRef = GetHaddoBooksFieldInRow(m_sHaddoHandle, COL_cover_ref, iRow)
        Dim sfnFromCover As String: sfnFromCover = ResolveCoverRefToFile(sCoverRef)
        Debug.Assert FileExists(sfnFromCover)
        
        ' position and resize
        Dim shp As Shape: Set shp = PositionImage(sfnFromCover, rAnchor, N_CoverHeightInRows, N_CoverWidthInCols)
        shp.OnAction = S_ShapeClicked

        ' show info below the cover
        Dim bIsURL As Boolean: bIsURL = StartsWith(sCoverRef, "https://")
        Dim sVisualBookID As String: sVisualBookID = IIf(bIsURL, GetHaddoBooksFieldInRow(m_sHaddoHandle, COL_isbn13, iRow), sCoverRef)
        With rAnchor.Offset(N_CoverHeightInRows)
            .NumberFormat = "@"
            .Font.Color = GRAY
            .Font.Size = 6
            .Value2 = sVisualBookID
        End With
        
        Dim sRack As String: sRack = GetHaddoBooksFieldInRow(m_sHaddoHandle, COL_space_label, iRow)
        Dim sBin As String: sBin = GetHaddoBooksFieldInRow(m_sHaddoHandle, COL_bin_label, iRow)
        Dim sPosition As String: sPosition = GetHaddoBooksFieldInRow(m_sHaddoHandle, COL_position, iRow)
        Dim sRackBin As String: sRackBin = FS("# / # (#)", RegMatch(sRack, "[0-9]+", 0), RegMatch(sBin, "[0-9]+", 0), sPosition)
        With rAnchor.Offset(N_CoverHeightInRows, 1)
            .NumberFormat = "@"
            .Font.Color = BLACK
            .Font.Size = 6
            .Value2 = sRackBin
        End With
        
        ' show tags
        With rAnchor.Offset(N_CoverHeightInRows + 1)
            .Value2 = GetHaddoBooksFieldInRow(m_sHaddoHandle, COL_tags, iRow)
            .Font.Bold = True
            .Font.Size = 6
        End With
                
        ' move anchor right, or "CRLF"
        If ixCoverInRow < N_CoversPerRow Then
            Set rAnchor = rAnchor.Offset(0, N_HorizontalOffsetToNextCover)
            ixCoverInRow = ixCoverInRow + 1
        Else
            Set m_rRowAnchor = m_rRowAnchor.Offset(N_VerticalOffsetToNextRowOfCovers)
            Set rAnchor = m_rRowAnchor
            ixCoverInRow = 1
        End If
    Next
    
    ' Debug.Print TimerElapsedStr
done:
    RevertApplicationState
End Sub


Function ResolveCoverRefToFile(sCoverRef As String) As String
    If sCoverRef = "" Then sCoverRef = NO_BOOK_COVER_URL
    ResolveCoverRefToFile = DetermineQualifiedImagePath(sCoverRef)
End Function

