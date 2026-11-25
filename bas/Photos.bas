Attribute VB_Name = "Photos"
Option Explicit

'*************************************
' Photos, Source + Protocol
'*************************************

Sub StoreSourcePhotosInProtocolForAllRacks()
    ' 30.06.26 das funktioniert vermutlich nicht mehr
    Debug.Assert False
    Dim ixRack As Integer
    For ixRack = 1 To N_RACKS
        StoreSourcePhotosInProtocolForRack ixRack
    Next
End Sub


Sub StoreSourcePhotosInProtocolForRack(iPassedRack As Integer)
    Dim cProtocolPhotoCellsForRack As Collection: Set cProtocolPhotoCellsForRack = CollectProtocolPhotoCellsForRack(iPassedRack)
    Dim cSourcePhotosForRack As Collection: Set cSourcePhotosForRack = CollectSourcePhotosForRack(iPassedRack)
    
    Dim nPhotos As Integer: nPhotos = cSourcePhotosForRack.Count
    Debug.Assert cProtocolPhotoCellsForRack.Count = nPhotos
    
    Dim res
    Dim ixPhoto As Integer
    For ixPhoto = 1 To nPhotos
        Dim rProtocolPhotoCell As Range: Set rProtocolPhotoCell = cProtocolPhotoCellsForRack(ixPhoto)
        Dim sProtocolPhoto As String: sProtocolPhoto = rProtocolPhotoCell.Value2
        Dim sSourcePhoto As String: sSourcePhoto = cSourcePhotosForRack(ixPhoto)
        If sProtocolPhoto = "" Then
            rProtocolPhotoCell.Value2 = sSourcePhoto
            Debug.Print FS("Protocol # := #", rProtocolPhotoCell.Address, sSourcePhoto)
        Else
            If sProtocolPhoto <> sSourcePhoto Then
                Dim sWarning As String: sWarning = FS("Protocol # (#) <> Source (#)", rProtocolPhotoCell.Address, sProtocolPhoto, sSourcePhoto)
                Debug.Print sWarning
                res = MsgBox(sWarning & ", continue?", vbYesNoCancel)
                If res = vbYes Then Exit Sub
            End If
        End If
    Next
End Sub


Function CollectSourcePhotosForRack(iPassedRack As Integer) As Collection
    CreateDataSheets False
    
    Dim cPhotos As New Collection
    Dim rImport As Range: Set rImport = PhotosDataSheet.GetRangeByHeader(H_Import)
    Dim rRack As Range: Set rRack = PhotosDataSheet.GetRangeByHeader(H_Rack)

    Dim ixCell As Integer
    For ixCell = 1 To rImport.Cells.Count
        If rRack.Cells(ixCell) = iPassedRack Then
            cPhotos.Add CStr(rImport.Cells(ixCell))
        End If
    Next
    Set CollectSourcePhotosForRack = cPhotos
End Function


Function CollectProtocolPhotoCellsForRack(iPassedRack As Integer) As Collection
    CreateDataSheets False
    
    Dim cPhotos As New Collection
    Dim rRacks As Range: Set rRacks = ProtocolDataSheet.GetRangeByHeader(H_Rack)
    Dim rProtocols As Range: Set rProtocols = ProtocolDataSheet.GetRangeByHeader(H_Protocol)
    Dim rProtocolPhotos As Range: Set rProtocolPhotos = ProtocolDataSheet.GetRangeByHeader(H_Photo)
    Dim ixCell As Integer
    Dim rRack As Range
    For ixCell = 1 To rRacks.Cells.Count
        If rRacks.Cells(ixCell) = iPassedRack Then
            If rProtocols.Cells(ixCell) = "||PH||" Then
                Dim rProtocolPhoto As Range: Set rProtocolPhoto = rProtocolPhotos.Cells(ixCell)
                cPhotos.Add rProtocolPhoto
                'Debug.Print rProtocolPhoto.Value2
            End If
        End If
    Next
    
    Set CollectProtocolPhotoCellsForRack = cPhotos
End Function


