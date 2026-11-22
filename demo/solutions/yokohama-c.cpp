#include<bits/stdc++.h>
using namespace std;

signed main()
{
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    int n;
    cin>>n;
    vector<int> b(n);
    for(int &x:b) cin>>x;
    int cut=min_element(b.begin(),b.end())-b.begin();
    int base=b[cut],peak=*max_element(b.begin(),b.end());
    long long rises=0;
    for(int i=0;i<n;i++) rises+=max(0,b[i]-b[(i+n-1)%n]);
    long long ans=max((long long)peak,rises);
    cout<<ans<<'\n';
    if(ans>200000) return 0;

    // Cut at the minimum. Above that baseline each level has disjoint runs.
    vector<vector<int> > starts(peak-base),ends(peak-base);
    for(int step=1;step<=n;step++)
    {
        int i=(cut+step)%n,prev=(i+n-1)%n;
        for(int h=b[prev];h<b[i];h++) starts[h-base].push_back(i+1);
        for(int h=b[i];h<b[prev];h++) ends[h-base].push_back(prev+1);
    }
    for(int h=0;h<(int)starts.size();h++)
    {
        int k=starts[h].size(),shift=min(base,k-1);
        // Rotating the ends forward by one covers each day one more time.
        for(int j=0;j<k;j++)
            cout<<starts[h][j]<<' '<<ends[h][(j+shift)%k]<<'\n';
        base-=shift;
    }
    while(base-->0) cout<<1<<' '<<n<<'\n';
    return 0;
}
