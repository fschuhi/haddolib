Attribute VB_Name = "Consts"
Option Explicit

Public Const N_RACKS = 14

' ShapeClick
Public Const M_AppName = "HaddolibApp"
Public Const S_ShapeClicked = "ShapeClicked"

' RackBoxes
Public Const MAX_BOXES_PER_RACK = 25 ' 5x5 Kallax

' Images
Public Const PICTURE_PATH = "y:\Projects\haddolib\data\photos\"
Public Const COVERS_PATH = "y:\Projects\haddolib\data\covers\"

' Worksheets
Public Const WS_ISBNsInput = "ISBNs (input)"
Public Const WS_ISBNdb = "ISBNdb"
Public Const WS_Protocol = "Protocol"
Public Const WS_Photos = "Photos"
Public Const WS_RackBoxShelf = "Rack+Box (shelf)"
Public Const WS_TagsShelf = "Tags (shelf)"
Public Const WS_AuthorsShelf = "Authors (shelf)"
Public Const WS_TitleShelf = "Title (shelf)"

' named ranges
Public Const R_Headers = "Headers"
Public Const R_Anchor = "Anchor"
Public Const R_Tags = "Tags"
Public Const R_MustAllMatch = "MustAllMatch"
Public Const R_Authors = "Authors"
Public Const R_Title = "Title"

' headers on "Protocol"
Public Const H_PH = "||PH||"
Public Const H_Rack = "rack" ' also on Photos
Public Const H_Box = "box"
Public Const H_Protocol = "protocol"
Public Const H_Tags = "tags"
Public Const H_Photo = "photo"
Public Const H_Key = "key"

' headers on "ISBNdb"
Public Const H_ISBN13 = "isbn13"
Public Const H_ISBN10 = "isbn10"
Public Const H_Title = "title"
Public Const H_Authors = "authors"
Public Const H_Publisher = "publisher"
Public Const H_DatePublished = "date_published"
Public Const H_Pages = "pages"
Public Const H_Binding = "binding"
Public Const H_Height = "height_cm"
Public Const H_Length = "length_cm"
Public Const H_Width = "width_cm"
Public Const H_Weight = "weight_kg"
Public Const H_Subjects = "subjects"

' headers on Photos
Public Const H_Import = "import"

' headers on both "Protocol" and "ISBNdb"
Public Const H_CoverURL = "cover_url"

' clHaddoBookshelf
Public Const NO_BOOK_COVER_URL = "https://images.isbndb.com/covers/5235723483541.jpg"

' Haddolib, RackBoxes, clHaddoBookshelf
Public Const S_Magazin = "Magazin"
Public Const R_DbImport = "DbImportRange"

' Tags (shelf)
Public Const H_MatchAll = "MustAllMatch"

' HaddoLib
Public Const R_Touchpoint = "Touchpoint"
