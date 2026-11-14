library(tidytext)
comments %>% unnest_tokens(word, text) %>% count(theme, word, sort = TRUE)
