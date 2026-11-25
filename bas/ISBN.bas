Attribute VB_Name = "ISBN"
Option Explicit

'*************************************
' ISBN validation
'*************************************

Function CheckISBN(sISBN As String) As Boolean
    ' Remove hyphens and spaces
    Dim s As String
    s = Replace(sISBN, "-", "")
    s = Replace(s, " ", "")
    s = UCase(s)
    
    ' Must be either 10 or 13 characters
    If Len(s) <> 10 And Len(s) <> 13 Then
        CheckISBN = False
        Exit Function
    End If
    
    ' =========================
    ' ISBN-13 Validation
    ' =========================
    If Len(s) = 13 Then
    
        ' Must start with 978 or 979
        If Left(s, 3) <> "978" And Left(s, 3) <> "979" Then
            CheckISBN = False
            Exit Function
        End If
        
        ' All must be numeric
        If Not s Like String(13, "#") Then
            CheckISBN = False
            Exit Function
        End If
        
        Dim sum As Long: sum = 0
        
        ' First 12 digits
        Dim i As Integer
        For i = 1 To 12
            If i Mod 2 = 1 Then
                sum = sum + CInt(Mid(s, i, 1))
            Else
                sum = sum + 3 * CInt(Mid(s, i, 1))
            End If
        Next i
        
        Dim checkDigit As Integer: checkDigit = (10 - (sum Mod 10)) Mod 10
        
        CheckISBN = (checkDigit = CInt(Mid(s, 13, 1)))
        Exit Function
    End If
    
    
    ' =========================
    ' ISBN-10 Validation
    ' =========================
    If Len(s) = 10 Then
        
        ' First 9 must be numeric
        If Not Left(s, 9) Like String(9, "#") Then
            CheckISBN = False
            Exit Function
        End If
        
        sum = 0
        
        For i = 1 To 9
            sum = sum + i * CInt(Mid(s, i, 1))
        Next i
        
        checkDigit = sum Mod 11
        
        ' Last digit may be X (meaning 10)
        If Mid(s, 10, 1) = "X" Then
            CheckISBN = (checkDigit = 10)
        ElseIf Mid(s, 10, 1) Like "#" Then
            CheckISBN = (checkDigit = CInt(Mid(s, 10, 1)))
        Else
            CheckISBN = False
        End If
        
    End If
    
End Function


'*************************************
' ISBN-10 to ISBN-13 conversion
'*************************************

Function ISBN10To13(sISBN10 As String) As String
    ' Return empty string on any failure
    ISBN10To13 = ""
    
    ' Clean the input the same way CheckISBN does
    Dim s As String
    s = Replace(sISBN10, "-", "")
    s = Replace(s, " ", "")
    s = UCase(s)
    
    ' Must be a valid ISBN-10 before we proceed
    If Not CheckISBN(s) Then
        Exit Function
    End If
    If Len(s) <> 10 Then
        Exit Function
    End If
    
    ' Build the first 12 digits of the ISBN-13:
    ' prepend "978" and take the first 9 digits of the ISBN-10
    ' (dropping its own check digit)
    Dim s12 As String
    s12 = "978" & Left(s, 9)
    
    ' Compute the ISBN-13 check digit over the 12-digit stem
    Dim sum As Long: sum = 0
    Dim i As Integer
    For i = 1 To 12
        If i Mod 2 = 1 Then
            sum = sum + CInt(Mid(s12, i, 1))
        Else
            sum = sum + 3 * CInt(Mid(s12, i, 1))
        End If
    Next i
    
    Dim checkDigit As Integer
    checkDigit = (10 - (sum Mod 10)) Mod 10
    
    ISBN10To13 = s12 & CStr(checkDigit)
End Function


'*************************************
' ISBN helpers (deprecated)
'*************************************

Sub TouchISBNs()
    SetSilentApplicationState
    Dim wsISBNdb As Worksheet: Set wsISBNdb = Worksheets(WS_ISBNdb)
    Dim rAnchor As Range: Set rAnchor = wsISBNdb.Range("T2")
    Dim rISBNs As Range: Set rISBNs = wsISBNdb.Range(rAnchor, rAnchor.End(xlDown))
    
    Dim rISBN As Range
    For Each rISBN In rISBNs
        If rISBN.PrefixCharacter = "'" Then
            Dim v: v = CStr(rISBN.value)
            rISBN.Clear
            rISBN.NumberFormat = "@"
            rISBN.value = ""
            rISBN.value = v
        End If
    Next
    RevertApplicationState
End Sub


Sub ConvertNumericISBN10ToText()
    SetSilentApplicationState
    Dim wsISBNdb As Worksheet: Set wsISBNdb = Worksheets(WS_ISBNdb)
    
    Dim rAnchor13 As Range: Set rAnchor13 = wsISBNdb.Range("A2")
    Dim rISBN13s As Range: Set rISBN13s = wsISBNdb.Range(rAnchor13, rAnchor13.End(xlDown))
    Dim nISBN13s As Long: nISBN13s = rISBN13s.Cells.Count
    
    Dim rAnchor10 As Range: Set rAnchor10 = wsISBNdb.Range("T2")
    Dim ixISBN10 As Integer
    For ixISBN10 = 1 To nISBN13s
        Dim rISBN10 As Range: Set rISBN10 = rAnchor10.Offset(ixISBN10 - 1)
        If IsNumeric(rISBN10.Value2) Then
            rISBN10.Value2 = "'" & rISBN10.Value2
        End If
    Next
    RevertApplicationState
End Sub



