

###################### query ########################
# select
# 0: Normal URL token tree
# 1: Regex URL token tree
treeDict = dict()
treeDict["filter_setup_001"] = ("""SELECT filter_string FROM TBL_FILTER_SETUP WHERE filter_type='FT001' order by filter_string desc
""", 0)

treeDict["filter_setup_002"] = ("""SELECT filter_string FROM TBL_FILTER_SETUP WHERE filter_type='FT002'
""", 0)

treeDict["filter_setup_003"] = ("""SELECT filter_string FROM TBL_FILTER_SETUP WHERE filter_type='FT003'
""", 1)

treeDict["filter_setup_004"] = ("""SELECT filter_string FROM TBL_FILTER_SETUP WHERE filter_type='FT004'
""", 1)

treeDict["filter_white_url"] = ("""SELECT host_name || NVL(uri, '') FROM tbl_white_url
""", 0)

keywordQuery = """SELECT DISTINCT KEY_NO, WEIGHTED_VALUE, KEYWORD_HEX
			FROM
			(
				SELECT B.KEY_NO, A.WEIGHTED_VALUE, B.KEYWORD_HEX
				FROM TBL_KEYWORD_HEX B, TBL_KEYWORD A
				WHERE A.KEY_NO = B.KEY_NO AND B.ENCODING_SET = 'ES001'
			)
			WHERE KEY_NO IN (SELECT KEY_NO FROM TBL_KEYWORD_SET WHERE KEY_GROUP_NO = {});
"""

# update

# insert
