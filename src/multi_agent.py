import re as regex
from base.agent import Agent
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI

from prompts import PROMPT_CHOOSE_TOOL, PROMPT_ANSWER, PROMPT_GET_MEMORY, PROMPT_ADVANCED_QUERY, PROMPT_SELECT_MATCHING_DESCRIPTION, PROMPT_REWRITE_DESCRIPTION_RELY_ON_OVERVIEW, PROMPT_REWRITE_DESCRIPTION, PROMPT_CHOOSE_SCENE, PROMPT_CHOOSE_DESCRIPTION4SCENE, PROMPT_WRITE_OVERALL_DESCRIPTION, PROMPT_CREATE_SCENARIO, PROMPT_UPDATE_SCENARIO


class MultiAgent(object):
    def __init__(self, llm: object, ):
        self.agent_choose_tool = Agent(
            system_prompt = "You are a helpful assistant.",
            prompt = PROMPT_CHOOSE_TOOL,
            llm = llm
        )
        self.agent_answer = Agent(
            system_prompt = "You are a helpful assistant",
            prompt = PROMPT_ANSWER,
            llm = llm
        )

        self.agent_get_memory = Agent(
            system_prompt = "You are an helpful assistant",
            prompt = PROMPT_GET_MEMORY,
            llm = llm
        )

        self.agent_advanced_query = Agent(
            system_prompt = "You are a marketing expert",
            prompt = PROMPT_ADVANCED_QUERY,
            llm = llm
        )

        self.agent_select_matching_description = Agent(
            system_prompt = "You are a marketing expert that analyze these video descriptions below and select some descriptions to make a good marketing video",
            prompt = PROMPT_SELECT_MATCHING_DESCRIPTION,
            llm = llm
        )
        
        self.agent_rewrite_description_rely_on_overview = Agent(
            system_prompt = "You are a marketing expert",
            prompt = PROMPT_REWRITE_DESCRIPTION_RELY_ON_OVERVIEW,
            llm = llm
        )
        
        self.agent_rewrite_description = Agent(
            system_prompt = "You are a marketing expert that analyze these video descriptions below and select some descriptions to make a good marketing video",
            prompt = PROMPT_REWRITE_DESCRIPTION,
            llm = llm
        )
        
        self.agent_choose_scene = Agent(
            system_prompt = "You are a review expert that analyze the video description and classify in appropriate scene",
            prompt = PROMPT_CHOOSE_SCENE,
            llm = llm
        )
        
        self.agent_choose_description4scene = Agent(
            system_prompt = "You are a review expert that analyzes descriptions and select the most relevant description",
            prompt = PROMPT_CHOOSE_DESCRIPTION4SCENE,
            llm = llm
        )
        
        self.agent_write_overall_description = Agent(
            system_prompt = "You are a review expert that analyzes descriptions and select the most relevant description",
            prompt = PROMPT_WRITE_OVERALL_DESCRIPTION,
            llm = llm
        )
        
        self.agent_create_scenario = Agent(
            system_prompt = "You are an AI assisstant",
            prompt = PROMPT_CREATE_SCENARIO,
            llm = llm
        )
        
        self.agent_update_scenario = Agent(
            system_prompt = "You are an AI assisstant",
            prompt = PROMPT_UPDATE_SCENARIO,
            llm = llm
        )
        
    async def choose_tool(self, query: str, memory: list):
        def OutputStructured(BaseModel):
            """Format the response as JSON including the response of chatbot, with key is 'tool'"""

        result = await self.agent_choose_tool(OutputStructured, query=query, memory=memory)
        print(f"----choose_tool: {result}")
        return result
    
    async def answer(self, query: str, memory: list):
        def OutputStructured(BaseModel):
            """Format the response as JSON including the response of chatbot, with keys are 'response' and 'new_query'"""

        result = await self.agent_answer(OutputStructured, query=query, memory=memory)
        print(f"----answer: {result}")
        return result
    
    async def get_memory(self, query: str, message: str):
        def OutputStructured(BaseModel):
            """Format the response as JSON with value is text and key is 'result'"""

        result = await self.agent_get_memory(OutputStructured, query=query, message=message)
        print(f"----get_memory: {result}")
        return result
    
    async def get_advanced_query(self, query: str, scene_dict: dict):
        def OutputStructured(BaseModel):
            f"""Format the response as JSON with key is {list(scene_dict.keys())} and value is the advanced query."""
            result: dict = Field(description="keys and advanced queries")

        result = await self.agent_advanced_query(OutputStructured, query=query, scene_dict=scene_dict)
        print(f"----get_advanced_query: {result}")
        return result
    
    async def select_matching_description(self, query: str, descriptions: dict):
        def OutputStructured(BaseModel):
            """Format the response as JSON with key is the scene name and value is the video ID of the most reasonable description in each scene"""
            result: dict = Field(description="scene name and video ID")

        result = await self.agent_select_matching_description(OutputStructured, query=query, descriptions=descriptions)
        print(f"----select_matching_description: {result}")
        return result
    
    async def rewrite_description_rely_on_overview(self, overview: str, description_parts: dict):
        def OutputStructured(BaseModel):
            """Format the response as JSON with value is new description and key is video ID"""
            result: dict = Field(description="video ID and new description")

        result = await self.agent_rewrite_description_rely_on_overview(OutputStructured, overview=overview, descriptions=description_parts)
        print(f"----rewrite_description_rely_on_overview: {result}")
        return result
    
    async def rewrite_description(self, query: str, descriptions: dict):
        def OutputStructured(BaseModel):
            """Format the response as JSON with value is a dictionary including scene name and new description"""
            result: dict = Field(description="scene name and new description")

        result = await self.agent_rewrite_description(OutputStructured, query=query, descriptions=descriptions)
        print(f"----rewrite_description: {result}")
        return result
    
    async def choose_scene(self, scene_dict: str, descriptions: dict, category: str):
        def OutputStructured(BaseModel):
            """Format the response as JSON with key is the id video and value is the name of scene"""
            result: dict = Field(description="id video and name of scene")
            
        if category:
            list_category = regex.sub(r",\s+", ",", category).split(",")
            scene_dict = {k:v for k, v in scene_dict.items() if k in list_category}

        result = await self.agent_choose_scene(OutputStructured, scene_dict=scene_dict, descriptions=descriptions)
        print(f"----choose_scene: {result}")
        return result
    
    async def choose_description4scene(self, scene_dict: str, descriptions: dict):
        def OutputStructured(BaseModel):
            """Format the response as JSON with key is the scene name, and value is the video id of the most relevant description"""
            result: dict = Field(description="scene name and video id")

        result = await self.agent_choose_description4scene(OutputStructured, scene_dict=scene_dict, descriptions=descriptions)
        print(f"----choose_description4scene: {result}")
        return result
    
    async def write_overall_description(self, description_parts: dict):
        def OutputStructured(BaseModel):
            """Format the response as JSON with key is 'result' and value is the overall description"""
            result: str = Field(description="the overall description")

        result = await self.agent_write_overall_description(OutputStructured, descriptions=description_parts)
        print(f"----write_overall_description: {result}")
        return result
    
    async def create_scenario(self, query: str):
        def OutputStructured(BaseModel):
            """Format the response as JSON with key is scene name and value is scene description"""
            result: dict = Field(description="scene name and description")

        result = await self.agent_create_scenario(OutputStructured, query=query)
        print(f"----create_scenario: {result}")
        return result

    async def update_scenario(self, scene_des: dict):
        def OutputStructured(BaseModel):
            """Format the response as JSON with key is no name scene and value is new scene name"""
            result: str = Field(description="no name scene and new scene name")

        result = await self.agent_update_scenario(OutputStructured, scene_des=scene_des)
        print(f"----update_scenario: {result}")
        return result