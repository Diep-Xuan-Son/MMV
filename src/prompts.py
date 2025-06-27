PROMPT_CHOOSE_TOOL = """
The user's query: {query}

Here is your memory: {memory}

Here is the tools:
{{
    "Q&A": using this tool if the user doesn't provide enough description for the video or the user is greeting
    "create_video": using this tool if you had enough description about the video
}}

## TASKS
- Depending on the user's query and your memory, please choose the appropriate tool 

Format the response as JSON like below: 
{{
    "tool": <the best tool>
}}
"""

PROMPT_ANSWER = """
The user's query: {query}

Here is your memory: {memory}

## TASKS
- Understand the demands of user and answer the user's questions.
- Your ability is to create marketing videos Hence you should direct the user to create video what the user want
- Based on your memory and the user's query, write a new query with comprehensive information synthesis for the user 

Format the response as JSON like below: 
{{
    "response": <the response of chatbot to answer the user's query>,
    "new_query": <new query of the user>
}}

## RULES
- The response must be in Vietnamese
- Don't greet the user too much, especially if you have already said that
"""
# - Based on the user's query, you should set flag 'create_video' is True if the user has enough description about video and set flag 'create_video' is False if the user doesn't have description about video

PROMPT_GET_MEMORY = """
You are a helpful assistant with the ability to brief the message as a memory for the future

To brief message you need to rely on the user's query
You have to write a short sentence to brief the conversation between you and the user.
If having any problem you have not yet done for the user, please provide me

Here is the user's query: {query}
Here is your message: {message}  
"""



PROMPT_ADVANCED_QUERY = """
The user's query: {query}
Scenes and their descriptions: {scene_dict}

## TASKS
- Based on the definitions of scenes below and the user's query, rewrite an advanced query for each specific scene. 
- Advanced query need to get full information of the user's query

Format the response as JSON like below: 
{{
    <name of key>: <advanced query>,
}}
"""

PROMPT_SELECT_MATCHING_DESCRIPTION = """
The user's query: {query}
The scene descriptions: {descriptions}

## TASKS
- Based on the user's query, select the most reasonable description that matches with the demand of the user in each scene.
"""

PROMPT_REWRITE_DESCRIPTION_RELY_ON_OVERVIEW = """
The overview: {overview}
Video IDs and their descriptions: {descriptions}

Based on the overview, rewrite a new description that is more reasonable for each video

The new description is in Vietnamese 
"""

PROMPT_REWRITE_DESCRIPTION = """
The user's query: {query}

Scene name and their descriptions: {descriptions}

Doing these tasks below to make a good marketing video:
- Based on the user's query rewriting the new description for these scenes to make a introducing video. 
- Using conjunctions in the new desciptions to form a cohesive introduce paragraph.

## RULE 
Format the response as JSON type like below:
{{
    <scene name>: <new description>
}}
Let's INTRODUCE, don't DESCRIBE
The number of words in each description is under 80 words
The new description is in Vietnamese 
"""

PROMPT_CHOOSE_SCENE = """
The video descriptions: {descriptions}

## TASKS
- Based on the definitions of scenes below, select the best scene that matches with each video description.

Scenes and their definitions: {scene_dict}
"""

PROMPT_CHOOSE_DESCRIPTION4SCENE = """
Some of descriptions for each scene: {descriptions}

Based on the definitions of scenes below, select the most relevant description with each scene.
Scenes and their definitions: {scene_dict}
"""


PROMPT_WRITE_OVERALL_DESCRIPTION = """
The descriptions for each part of video: {descriptions}

Based on the description of each part video, Write an overall description that gives an overview of the video content.

## RULE
Write the overall description in Vietnamese
"""