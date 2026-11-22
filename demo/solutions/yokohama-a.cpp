#include<bits/stdc++.h>
using namespace std;

signed main()
{
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    int n;
    long long length;
    cin>>n>>length;
    vector<pair<long long,int> > a(n);
    for(auto &p:a) cin>>p.second>>p.first;
    if(n%2)
    {
        cout<<"no\n";
        return 0;
    }
    sort(a.begin(),a.end());
    int first=-1,inside=0,ans=0;
    for(int i=0;i<n;)
    {
        int j=i+1;
        while(j<n&&a[i].first==a[j].first) j++;
        if(j-i==2)
        {
            // A full column inside an odd prefix must release at least one tile.
            if(first!=-1) inside++;
        }
        else
        {
            int color=(a[i].first+a[i].second)%2;
            if(first==-1) first=color,inside=0;
            else
            {
                // Equal endpoint colors require an odd number of color flips.
                ans+=inside+((inside%2)!=(first==color));
                first=-1;
            }
        }
        i=j;
    }
    cout<<ans<<'\n';
    return 0;
}
