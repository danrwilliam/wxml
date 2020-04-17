import wxml
from wxml.bind import BindValue
from wxml.utils import NamedTupleSerializer
from typing import NamedTuple

class Movie(NamedTuple):
    title : str
    director : str
    year : int

MovieSerializer = NamedTupleSerializer(Movie)

wxml.bind.DEBUG_UPDATE=1

movie_value = BindValue(
    Movie('Star Wars', 'George Lucas', 1977),
    serialize=True,
    name='movie',
    serializer=MovieSerializer
)
#, serializer=NamedTupleSerializer(Movie))
print(movie_value)

wxml.bind.DataStore.save()