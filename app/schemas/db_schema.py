from pydantic import BaseModel


class SchemaColumn(BaseModel):
    name: str
    data_type: str


class SchemaTable(BaseModel):
    name: str
    columns: list[SchemaColumn]
