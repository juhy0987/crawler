

###################### query ########################
# select
selectDict = dict()
selectDict["filter_setup_001"] = ("""SELECT filter_string FROM TBL_FILTER_SETUP WHERE filter_type='FT001' order by filter_string desc
""", 0)

selectDict["filter_setup_002"] = ("""SELECT filter_string FROM TBL_FILTER_SETUP WHERE filter_type='FT002'
""", 0)

selectDict["filter_setup_003"] = ("""SELECT filter_string FROM TBL_FILTER_SETUP WHERE filter_type='FT003'
""", 1)

selectDict["filter_setup_004"] = ("""SELECT filter_string FROM TBL_FILTER_SETUP WHERE filter_type='FT004'
""", 1)

selectDict["filter_white_url"] = ("""SELECT host_name || NVL(uri, '') FROM tbl_white_url
""", 0)

# update

# insert
