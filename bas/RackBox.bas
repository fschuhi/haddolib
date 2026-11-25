Attribute VB_Name = "RackBox"
Dim g_cAllBoxes As Collection

'*************************************
' helpers
'*************************************

Function RackToString(iRack As Integer) As String
    RackToString = "rack " & Format(iRack, "00")
End Function

Function BoxToString(iBox As Integer) As String
    BoxToString = "box " & Format(iBox, "00")
End Function


'*************************************
' next/prev box
'*************************************

Private Function CollectAllBoxes() As Collection
    If g_cAllBoxes Is Nothing Then
        Set g_cAllBoxes = New Collection
        
        Dim sRacks As String: sRacks = HaddoSpaces(S_Magazin)
        Dim aRacks() As String: aRacks = Split(sRacks, ", ")
        
        Dim ixRack As Integer
        For ixRack = LBound(aRacks) To UBound(aRacks)
            Dim sRack As String: sRack = aRacks(ixRack)
            Dim sBoxes As String: sBoxes = HaddoBins(S_Magazin, sRack)
            Dim aBoxes() As String: aBoxes = Split(sBoxes, ", ")
            Dim ixBox As Integer
            For ixBox = LBound(aBoxes) To UBound(aBoxes)
                Dim sBox As String: sBox = aBoxes(ixBox)
                g_cAllBoxes.Add sRack & "/" & sBox
            Next
        Next
    End If
    Set CollectAllBoxes = g_cAllBoxes
End Function


Private Sub ParseRackBox(sRackBox As String, ByRef iRack As Integer, ByRef iBox As Integer)
    Const RE = "[A-Za-z]+ ([0-9]+)/[A-Za-z]+ ([0-9]+)"
    iRack = RegMatch(sRackBox, RE, 1) + 0
    iBox = RegMatch(sRackBox, RE, 2) + 0
End Sub


Sub DetermineNextBox(iPassedRack As Integer, iPassedBox As Integer, ByRef iNextRack As Integer, ByRef iNextBox As Integer)
    iNextRack = iPassedRack: iNextBox = iPassedBox
    Dim sPassedRackBox As String: sPassedRackBox = RackToString(iPassedRack) & "/" & BoxToString(iPassedBox)
    Dim cAllBoxes As Collection: Set cAllBoxes = CollectAllBoxes()
    
    Dim ixBox As Integer
    For ixBox = 1 To cAllBoxes.Count
        If cAllBoxes(ixBox) = sPassedRackBox Then
            If ixBox = cAllBoxes.Count Then
                MsgBox "no next box", vbExclamation
                Exit Sub
            Else
                Dim sNextRackBox As String: sNextRackBox = cAllBoxes(ixBox + 1)
                ParseRackBox sNextRackBox, iNextRack, iNextBox
                Exit Sub
            End If
        End If
    Next
    MsgBox "rack/box combo not found", vbExclamation
End Sub


Sub DeterminePrevBox(iPassedRack As Integer, iPassedBox As Integer, ByRef iPrevRack As Integer, ByRef iPrevBox As Integer)
    iPrevRack = iPassedRack: iPrevBox = iPassedBox
    Dim sPassedRackBox As String: sPassedRackBox = RackToString(iPassedRack) & "/" & BoxToString(iPassedBox)
    Dim cAllBoxes As Collection: Set cAllBoxes = CollectAllBoxes()
    
    Dim ixBox As Integer
    For ixBox = 1 To cAllBoxes.Count
        If cAllBoxes(ixBox) = sPassedRackBox Then
            If ixBox = 1 Then
                MsgBox "no previous box", vbExclamation
                Exit Sub
            Else
                Dim sPrevRackBox As String: sPrevRackBox = cAllBoxes(ixBox - 1)
                ParseRackBox sPrevRackBox, iPrevRack, iPrevBox
                Exit Sub
            End If
        End If
    Next
    MsgBox "rack/box combo not found", vbExclamation
End Sub


