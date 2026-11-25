VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
END
Attribute VB_Name = "clDataSheet"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Option Explicit

Const R_Header = "Header"

Dim m_wsISBNdb As Worksheet
Dim m_rHeader As Range
Dim m_rHeaderCols As Range
Dim m_rKeyHeaderCol As Range
Dim m_dictHeaderCols As New Dictionary
Dim m_rKeys As Range
Dim m_dictKeys As New Dictionary


Public Sub Init(wsDataSheet As Worksheet, sKeyHeaderCol As String)
    Set m_wsISBNdb = wsDataSheet
    LoadHeader
    Set m_rKeyHeaderCol = m_dictHeaderCols(sKeyHeaderCol)
    LoadKeysAndRows
End Sub


Sub LoadHeader()
    Set m_rHeader = m_wsISBNdb.Range(R_Header)
    Set m_rHeaderCols = m_rHeader.SpecialCells(xlCellTypeConstants)
    Dim rHeaderCol As Range
    For Each rHeaderCol In m_rHeaderCols
        If IsEmpty(rHeaderCol) Then
            ' this should not happen, but it does
        Else
            Dim vKey: vKey = rHeaderCol.Value2
            If m_dictHeaderCols.Exists(vKey) Then
                ' we ignore duplicate fields
            Else
                m_dictHeaderCols.Add vKey, rHeaderCol
            End If
        End If
    Next
End Sub


Sub LoadKeysAndRows()
    Set m_rKeys = m_wsISBNdb.Range(m_rKeyHeaderCol.Offset(1), m_rKeyHeaderCol.End(xlDown))
    Dim bDuplicatesExist As Boolean
    Dim rKey As Range
    For Each rKey In m_rKeys
        Dim vKey: vKey = rKey.Value2
        If vKey = "NA" Then
            ' skip, ISBN10 not found via search
        Else
            If m_dictKeys.Exists(vKey) Then
                bDuplicatesExist = True
                Debug.Print "duplicate: " & vKey
            Else
                m_dictKeys.Add vKey, rKey
            End If
        End If
    Next
    'If m_dictKeys.Exists("11/01/01") Then Stop
    If bDuplicatesExist Then MsgBox "Duplicates exist, see direct window"
End Sub


Function GetHeaderCol(sHeader As String) As Range
    Set GetHeaderCol = m_dictHeaderCols(sHeader)
End Function


Public Function GetRangeByHeader(sHeader As String) As Range
    Dim rHeaderCol As Range: Set rHeaderCol = GetHeaderCol(sHeader)
    Set GetRangeByHeader = Intersect(m_rKeys.EntireRow, rHeaderCol.EntireColumn)
End Function


Public Function KeyExists(vKey) As Boolean
    KeyExists = m_dictKeys.Exists(vKey)
End Function

Public Function GetRowByKey(vKey) As Range
    Set GetRowByKey = m_dictKeys(vKey).EntireRow
End Function


Public Function GetCellInRowByHeader(sHeader As String, rRow As Range) As Range
    Set GetCellInRowByHeader = Intersect(GetHeaderCol(sHeader).EntireColumn, rRow.EntireRow)
End Function


Public Function GetCellByKeyAndHeader(vKey, sHeader As String) As Variant
    Dim rRow As Range: Set rRow = GetRowByKey(vKey).EntireRow
    Set GetCellByKeyAndHeader = GetCellInRowByHeader(sHeader, rRow)
End Function


Public Function GetValueByKeyAndHeader(vKey, sHeader As String) As Variant
    GetValueByKeyAndHeader = GetCellByKeyAndHeader(vKey, sHeader).Value2
End Function


Public Function CollectKeyCells(cKeys As Collection) As Collection
    Dim cKeyCells As New Collection
    Dim vKey
    For Each vKey In cKeys
        Dim rKey As Range: Set rKey = m_dictKeys(vKey)
        cKeyCells.Add rKey
    Next
    Set CollectKeyCells = cKeyCells
End Function
