struct point{
    int x;
    char y ;
}

struct line{
    struct point p1 ;
    struct point p2 ;
}

int main()
{
    struct line l1 ;
    l1.p1.x = 5 ;
    l1.p2.z = 4 ;
    return 0;
}