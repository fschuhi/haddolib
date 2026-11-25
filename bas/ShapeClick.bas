Attribute VB_Name = "ShapeClick"
Option Explicit

' a "book sheet" is a clHaddoBookshelf
Private m_BookSheets As New Dictionary

Private m_shpLastClick As String
Private m_dLastClickTime As Double


'*************************************
' register/Unregister
'*************************************

' we use a dictionary for untyped registrations, but we enforce it via typed register/Unregister

Public Sub RegisterHaddoBookshelf(shelf As clHaddoBookshelf, ws As Worksheet)
    Set m_BookSheets(ws.CodeName) = shelf
End Sub

Public Sub UnregisterHaddoBookshelf(ws As Worksheet)
    If m_BookSheets.Exists(ws.CodeName) Then m_BookSheets.Remove ws.CodeName
End Sub


'*************************************
' register/Unregister
'*************************************

Public Sub ShapeClicked()
    Dim sClickedName As String: sClickedName = Application.Caller

    Dim shp As Shape: Set shp = ActiveSheet.Shapes(sClickedName)

    ' Double-click detection
    If sClickedName = m_shpLastClick And (Timer - m_dLastClickTime) < 0.5 Then
        m_shpLastClick = ""
        m_dLastClickTime = 0

        Dim sCodeName As String: sCodeName = ActiveSheet.CodeName

        If Not m_BookSheets.Exists(sCodeName) Then
            Debug.Print "No shelf registered for sheet: " & sCodeName
            Exit Sub
        End If

        ' book sheet is a clHaddoBookshelf
        Dim vBookSheet: Set vBookSheet = m_BookSheets(sCodeName)
        
        ' all three classes have a HandleShapeClicked
        vBookSheet.HandleShapeClicked shp.TopLeftCell
    Else
        m_shpLastClick = sClickedName
        m_dLastClickTime = Timer
    End If
End Sub
