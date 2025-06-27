from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage
import re as regex
from string import Formatter

class Agent():
    def __init__(self, system_prompt, prompt, llm):
        self.system_prompt = system_prompt
        self.prompt = prompt
        self.llm = llm
        
    async def __call__(self, OutputStructured, **kwargs):
        input_variables = {
            v for _, v, _, _ in Formatter().parse(self.prompt) if v is not None
        }
        for i in input_variables:
            assert i in list(kwargs.keys()), f"Don't have argument {i}"
        
        prompt = self.prompt.format(**kwargs)
        structured_output = self.llm.with_structured_output(OutputStructured)
        chat_prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=prompt)
            ]
        )

        chain = chat_prompt | structured_output 
        response = await chain.ainvoke({})
        return response
    
    
