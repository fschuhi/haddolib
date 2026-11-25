Attribute VB_Name = "Haddolib"
Option Explicit

'*************************************
' PyXLL wrappers
'*************************************

Public Function VBA_haddo_query(ByVal name As String, Optional ByVal param1 As Variant, Optional ByVal param2 As Variant) As Variant
    Const FN_haddo_query = "haddo_query"
    If IsMissing(param1) Then
        VBA_haddo_query = Application.Run(FN_haddo_query, name)
    ElseIf IsMissing(param2) Then
        VBA_haddo_query = Application.Run(FN_haddo_query, name, param1)
    Else
        VBA_haddo_query = Application.Run(FN_haddo_query, name, param1, param2)
    End If
End Function

Public Function VBA_haddo_books_by_bin(sRoom As String, sSpace As String, sBin As String) As String
    VBA_haddo_books_by_bin = Application.Run("haddo_books_by_bin", sRoom, sSpace, sBin)
End Function

Public Function VBA_haddo_books_by_title(sTitle As String) As String
    VBA_haddo_books_by_title = Application.Run("haddo_books_by_title", sTitle)
End Function

Public Function VBA_haddo_books_by_author(sAuthor As String) As String
    VBA_haddo_books_by_author = Application.Run("haddo_books_by_author", sAuthor)
End Function

Public Function VBA_haddo_books_by_tags(sTags As String, bMatchAll As Boolean) As String
    VBA_haddo_books_by_tags = Application.Run("haddo_books_by_tags", sTags, bMatchAll)
End Function

Public Function VBA_haddo_get_field(sHandle As String, iRow As Integer, sField As String) As Variant
    VBA_haddo_get_field = Application.Run("haddo_get_field", sHandle, iRow, sField)
End Function

Public Function VBA_haddo_set_tags(iBookID As Integer, sTags As String) As String
    VBA_haddo_set_tags = Application.Run("haddo_set_tags", iBookID, sTags)
End Function

Public Function VBA_haddo_tag_stats(Optional bOrderByCount As Boolean = True)
    VBA_haddo_tag_stats = Application.Run("haddo_tag_stats", bOrderByCount)
End Function

Public Function VBA_haddo_len(sHandle As String) As Integer
    VBA_haddo_len = Application.Run("haddo_len", sHandle)
End Function

Public Function VBA_haddo_release(sHandle As String) As String
    VBA_haddo_release = Application.Run("haddo_release", sHandle)
    Application.Calculate
End Function

Public Sub VBA_haddo_sweep_handles()
    Dim nSweeped As Integer: nSweeped = Application.Run("haddo_sweep_handles", 0)
    MsgBox FS("sweeped # handles", nSweeped)
    Application.Calculate
End Sub

Public Function VBA_haddo_handles() As Variant
    VBA_haddo_handles = Application.Run("haddo_handles")
End Function


'*************************************
' collect books
'*************************************

Public Function CollectHaddoBooksByBin(sRack As String, sBox As String) As String
    CollectHaddoBooksByBin = VBA_haddo_books_by_bin(S_Magazin, sRack, sBox)
End Function

Public Function CollectHaddoBooksByTitle(sTitle As String) As String
    CollectHaddoBooksByTitle = VBA_haddo_books_by_title(sTitle)
End Function

Public Function CollectHaddoBooksByAuthor(sAuthor As String) As String
    CollectHaddoBooksByAuthor = VBA_haddo_books_by_author(sAuthor)
End Function

Public Function CollectHaddoBooksByTags(sTags As String, bMatchAll As Boolean) As String
    CollectHaddoBooksByTags = VBA_haddo_books_by_tags(sTags, bMatchAll)
End Function

Public Function GetHaddoBooksLen(sHandle As String) As Integer
    GetHaddoBooksLen = VBA_haddo_len(sHandle)
End Function

Public Function GetHaddoBooksFieldInRow(sHandle As String, sField As String, iRow As Integer) As Variant
    Dim v: v = VBA_haddo_get_field(sHandle, iRow, sField)
    If Not IsNull(v) Then GetHaddoBooksFieldInRow = v
End Function

Public Function SetHaddoTags(iBookID As Integer, sTags As String) As String
    SetHaddoTags = VBA_haddo_set_tags(iBookID, sTags)
End Function

Public Function CollectTagStats(Optional bOrderByCount As Boolean = True)
    CollectTagStats = VBA_haddo_tag_stats(bOrderByCount)
End Function

Public Function ReleaseHaddoHandle(sHandle As String) As Boolean
    ReleaseHaddoHandle = VBA_haddo_release(sHandle) = "released"
End Function


'*************************************
' haddolib statistics
'*************************************

Function HaddoRooms() As String
    HaddoRooms = VBA_haddo_query("rooms")
End Function

Function HaddoSpaces(sRoom As String)
    HaddoSpaces = VBA_haddo_query("spaces", sRoom)
End Function

Function HaddoBins(sRoom As String, sSpace As String)
    HaddoBins = VBA_haddo_query("bins", sRoom, sSpace)
End Function

Function HaddoCountSpaces(sRoom As String)
    HaddoCountSpaces = VBA_haddo_query("space_count", sRoom)
End Function

Function HaddoCountAllBins()
    HaddoCountAllBins = VBA_haddo_query("location_combo_count")
End Function

Function HaddoCountBooks(Optional sRoom As String)
    HaddoCountBooks = VBA_haddo_query("book_count", sRoom)
End Function

Function HaddoCountBooksWithBib(Optional sRoom As String)
    HaddoCountBooksWithBib = VBA_haddo_query("book_count_with_bib", sRoom)
End Function

Function HaddoCountBooksWithOnlyPhoto(Optional sRoom As String)
    HaddoCountBooksWithOnlyPhoto = VBA_haddo_query("book_count_photo_only", sRoom)
End Function

Function HaddoCountBookStatus(sStatus As String, Optional sRoom As String)
    HaddoCountBookStatus = VBA_haddo_query("count_by_status", sStatus, sRoom)
End Function

Function HaddoCountRevisionSource(sSource As String, Optional sRoom As String)
    HaddoCountRevisionSource = VBA_haddo_query("count_by_revision_source", sSource, sRoom)
End Function

Function HaddoCountCoverStatus(sStatus As String, Optional sRoom As String)
    HaddoCountCoverStatus = VBA_haddo_query("count_by_cover_status", sStatus, sRoom)
End Function

Function HaddoCountCoverSource(sSource As String, Optional sRoom As String)
    HaddoCountCoverSource = VBA_haddo_query("count_by_cover_source", sSource, sRoom)
End Function

Function HaddoStatuses() As String
    HaddoStatuses = VBA_haddo_query("distinct_statuses")
End Function

Function HaddoRevisionSources() As String
    HaddoRevisionSources = VBA_haddo_query("distinct_revision_sources")
End Function

Function HaddoCoverStatuses() As String
    HaddoCoverStatuses = VBA_haddo_query("distinct_cover_statuses")
End Function

Function HaddoCoverSources() As String
    HaddoCoverSources = VBA_haddo_query("distinct_cover_sources")
End Function


