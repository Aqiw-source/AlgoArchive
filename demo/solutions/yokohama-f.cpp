// 附带用例是固定交互回放；实际评测须由交互器回答每个 measure 查询。
#include<bits/stdc++.h>
using namespace std;
using ll=long long;
using wide=__int128;
const int N=100;

int n,basis[3];
ll a[N][N];
bool known[N][N];

ll dot(int i,int j)
{
    if(!known[i][j])
    {
        cout<<"measure "<<i+1<<" "<<j+1<<endl;
        ll d;
        if(!(cin>>d) || d<0) exit(0);
        a[i][j]=a[j][i]=(a[i][i]+a[j][j]-d)/2;
        known[i][j]=known[j][i]=true;
    }
    return a[i][j];
}

wide determinant(wide g[4][4],int n)
{
    if(n==1) return g[0][0];
    wide res=0;
    for(int k=0;k<n;k++)
    {
        wide minor[4][4];
        for(int i=1;i<n;i++)
            for(int j=0,p=0;j<n;j++)
                if(j!=k) minor[i-1][p++]=g[i][j];
        wide term=g[0][k]*determinant(minor,n-1);
        res+=(k%2?-term:term);
    }
    return res;
}

// Append row i and column j to the basis Gram matrix.
// The resulting determinant is det(G)*a[i][j] plus its value at a[i][j]=0.
wide bordered(int r,int i,int j,ll corner)
{
    wide g[4][4];
    for(int u=0;u<r;u++)
    {
        for(int v=0;v<r;v++) g[u][v]=a[basis[u]][basis[v]];
        g[u][r]=a[basis[u]][j];
        g[r][u]=a[i][basis[u]];
    }
    g[r][r]=corner;
    return determinant(g,r+1);
}

signed main()
{
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    cin>>n;
    for(int i=0;i<n;i++) cin>>a[i][i],known[i][i]=true;
    int r=0;
    wide den=1;
    for(int i=0;i<n && r<3;i++)
    {
        wide det=bordered(r,i,i,a[i][i]);
        if(!det) continue;
        basis[r++]=i;
        den=det;
        for(int j=0;j<n;j++) dot(i,j);
    }
    cout<<"answer\n";
    for(int i=0;i<n-1;i++)
        for(int j=i+1;j<n;j++)
        {
            // All points lie in the span, so the bordered determinant is zero.
            ll prod=known[i][j]?a[i][j]:(ll)(-bordered(r,i,j,0)/den);
            cout<<a[i][i]+a[j][j]-2*prod<<(j==n-1?'\n':' ');
        }
    return 0;
}
