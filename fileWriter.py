with open("Output.txt", "w", encoding='UTF-8') as text_file:
    with open("wikiColors.txt", "r",  encoding='UTF-8', newline='') as read_file:
        for line in read_file:
            r = line.index("r=")
            r = line[r:line.index("|", r)]
            r = int(r[2:])
            
            g = line.index("g=")
            g = line[g:line.index("|", g)]
            g = int(g[2:])

            blu = line.index("b=")
            blu = line[blu:line.index("|", blu)]
            blu = int(blu[2:])

            name = line.index("name=")
            if "|" in line[name:]:
                name = line.index("|", name)
            elif "[[" in line[name:]:
                name = line.index("[[", name)
            name = line[name + 1:line.index("}", name)]
            #if "|" in line[3]:
            #    line[3] = line[3][line[3].index("|") + 1:]
            # noinspection PyTypeChecker
            print(name + "," + str(r) + "," + str(g) + "," + str(blu), file=text_file)
