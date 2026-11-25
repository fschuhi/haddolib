Attribute VB_Name = "BookShelves"
Option Explicit


Sub DisplayBooksInBox(iRack As Integer, iBox As Integer)
    Debug.Assert ActiveSheet.name = WS_RackBoxShelf
    ActiveSheet.Range(H_Rack) = iRack
    ActiveSheet.Range(H_Box) = iBox
    Dim sRack As String: sRack = RackToString(iRack)
    Dim sBox As String: sBox = BoxToString(iBox)
    Dim sHaddoHandle As String: sHaddoHandle = CollectHaddoBooksByBin(sRack, sBox)
    CreateHaddoBookshelf(ActiveSheet, sHaddoHandle).DisplayBooks
End Sub


Sub DisplayBooksForTags(sTags As String, bMatchAll As Boolean)
    Debug.Assert ActiveSheet.name = WS_TagsShelf
    ActiveSheet.Range(R_Tags) = sTags
    ActiveSheet.Range(R_MustAllMatch) = bMatchAll
    Dim sHaddoHandle As String: sHaddoHandle = CollectHaddoBooksByTags(sTags, bMatchAll)
    CreateHaddoBookshelf(ActiveSheet, sHaddoHandle).DisplayBooks
End Sub


Sub DisplayBooksForAuthors(sAuthors As String)
    Debug.Assert ActiveSheet.name = WS_AuthorsShelf
    ActiveSheet.Range(R_Authors) = sAuthors
    Dim sHaddoHandle As String: sHaddoHandle = CollectHaddoBooksByAuthor(sAuthors)
    CreateHaddoBookshelf(ActiveSheet, sHaddoHandle).DisplayBooks
End Sub


Sub DisplayBooksForTitle(sTitle As String)
    Debug.Assert ActiveSheet.name = WS_TitleShelf
    ActiveSheet.Range(R_Title) = sTitle
    Dim sHaddoHandle As String: sHaddoHandle = CollectHaddoBooksByTitle(sTitle)
    CreateHaddoBookshelf(ActiveSheet, sHaddoHandle).DisplayBooks
End Sub



